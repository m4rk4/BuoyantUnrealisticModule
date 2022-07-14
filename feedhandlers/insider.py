import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, unquote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    m = re.search(r'(i\.insider\.com/|image/)?([0-9a-f]+)', img_src)
    if m:
        return 'https://i.insider.com/{}?width={}&format=jpeg&auto=webp'.format(m.group(2), width)
    logger.warning('unknown image src ' + img_src)
    return img_src


def add_image(image):
    img_src = resize_image(image['links']['self'])
    captions = []
    caption = image['attributes'].get('caption')
    if caption:
        captions.append(caption)
    caption = image['attributes'].get('source')
    if caption:
        captions.append(caption)
    return utils.add_image(img_src, ' | '.join(captions))


def get_content(url, args, save_debug=False):
    content_json = utils.get_url_json(utils.clean_url(url) + '?app-shell')
    if not content_json:
        return None
    if save_debug:
        utils.write_file(content_json, './debug/debug.json')

    item = {}
    item['id'] = content_json['id']
    item['url'] = content_json['links']['site']
    item['title'] = content_json['attributes']['title']

    dt = datetime.fromisoformat(content_json['attributes']['published'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
    dt = datetime.fromisoformat(content_json['attributes']['modified'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    content_html = ''
    authors = []
    if content_json['relationships']['authors'].get('bylineAuthors'):
        for author in content_json['relationships']['authors']['bylineAuthors']:
            authors.append(author['attributes']['label'])
        for author in content_json['relationships']['authors']['data']:
            if author['attributes']['label'] not in authors:
                content_html += '<p><strong>{}</strong>&nbsp;&#9989;<br/><small>{}</small></p>'.format(author['attributes']['title'], author['attributes']['description'])
    else:
        for author in content_json['relationships']['authors']['data']:
            authors.append(author['attributes']['label'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if content_json['attributes'].get('categories'):
        item['tags'] = content_json['attributes']['categories'].copy()
    elif content_json['relationships']['categories'].get('data'):
        item['tags'] = []
        for tag in content_json['relationships']['categories']['data']:
            item['tags'].append(tag['attributes']['label'])

    #if content_json.get('summaryList'):
    #    content_html += content_json['summaryList']

    if content_json['attributes'].get('hero'):
        if content_json['attributes']['hero']['type'] == 'image':
            item['_image'] = content_json['attributes']['hero']['links']['self']
            content_html += add_image(content_json['attributes']['hero'])
    elif content_json['relationships']['images'].get('data'):
        item['_image'] = content_json['relationships']['images']['data'][0]['links']['self']

    item['summary'] = content_json['attributes']['description']

    soup = BeautifulSoup(content_json['attributes']['content'], 'html.parser')
    el = soup.find(id='piano-inline-content-wrapper')
    if el:
        content_html += str(el.decode_contents())
    else:
        logger.warning('unable to find content wrapper in ' + item['url'])

    if content_json['attributes']['format'] == 'slideshow':
        for slide in content_json['relationships']['slides']['data']:
            if slide['type'] == 'slide':
                content_html += '<h3>{}</h3>'.format(slide['attributes']['title'])
                if slide['relationships'].get('image') and slide['relationships']['image'].get('data'):
                    content_html += add_image(slide['relationships']['image']['data'])
                content_html += slide['attributes']['content']
                content_html += '<hr/>'
        if content_html.endswith('<hr/>'):
            content_html = content_html[:-5]

    elif content_json['attributes']['format'] == 'video':
        if content_json['relationships']['video']['data']['meta'].get('jwplayer'):
            it = utils.get_content('https://cdn.jwplayer.com/v2/media/{}'.format(
                content_json['relationships']['video']['data']['meta']['jwplayer']['assetID']), {"embed": True}, False)
            if it:
                item['_image'] = it['_image']
                content_html = it['content_html'] + content_html

    soup = BeautifulSoup(content_html, 'html.parser')

    for el in soup.find_all('figure'):
        if not el.get('class'):
            continue
        if 'image-figure-image' in el['class']:
            img_src = ''
            for img in el.find_all('img'):
                if img.get('src'):
                    if img['src'].startswith('https://i.insider.com'):
                        img_src = resize_image(img['src'])
            if img_src:
                captions = []
                it = el.find(class_='image-caption')
                if it:
                    captions.append(it.get_text())
                it = el.find(class_='image-source')
                if it:
                    captions.append(it.get_text())
                new_el = BeautifulSoup(utils.add_image(img_src, ' | '.join(captions)), 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unknown image src in ' + item['url'])
        else:
            logger.warning('unhandled figure class {} in {}'.format(el['class'], item['url']))

    for el in soup.find_all('style'):
        el.decompose()

    for el in soup.find_all(class_='insider-raw-embed'):
        #print(len(el.contents))
        if len(el.contents) == 0 or el.find('div', id=re.compile(r'div-gpt-ad-\d+')):
            el.decompose()
            continue
        new_html = ''
        it = el.find('iframe')
        if it:
            if it['src'].startswith('https://products.gobankingrates.com'):
                el.decompose()
                continue
            new_html = utils.add_embed(it['src'])
        else:
            it = el.find('blockquote')
            if it and it.get('class'):
                if 'tiktok-embed' in it['class']:
                    new_html = utils.add_embed(it['cite'])
            else:
                it = el.find('script')
                if it and it.get('data-telegram-post'):
                    logger.warning('unhandled Telegram embed in ' + item['url'])
                    el.decompose()
                    continue
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled insider-raw-embed in ' + item['url'])

    for el in soup.find_all('blockquote', class_='twitter-tweet'):
        links = el.find_all('a')
        new_html = utils.add_embed(links[-1]['href'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='iframe-container'):
        it = el.find('iframe')
        if it:
            new_html = utils.add_embed(it['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled iframe-container in ' + item['url'])

    for el in soup.find_all('iframe'):
        if el.get('src'):
            new_html = utils.add_embed(el['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled iframe in ' + item['url'])

    for el in soup.find_all(class_='product-card'):
        link = el.find('a', attrs={"data-analytics-product-id": True})
        if link:
            product = content_json['attributes']['productMap'][link['data-analytics-product-id']]
            img_src = resize_image(product['relationships']['image']['data']['links']['self'], 165)
            new_html = '<table><tr><td><img src="{}" /></td><td><strong>{}</strong><ul>'.format(img_src, product['attributes']['name'])
            for it in product['attributes']['purchaseOptions']:
                new_html += '<li><a href="{}">${} from {}</a></li>'.format(it['originalURL'], it['price']/100, it['merchant'])
            new_html += '</ul></td></tr></table>'
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled product-card in ' + item['url'])

    for el in soup.find_all(class_='category-stamp'):
        stamp = ''
        for it in el.find_all('svg'):
            if it['class'][0] == 'letter':
                stamp += it['class'][1]
        new_el = BeautifulSoup('<h2>{}</h2>'.format(stamp.title()), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('aside'):
        if 'quick-tip' in el['class'] or 'breakout-box' in el['class']:
            new_el = BeautifulSoup(utils.add_blockquote(el.decode_contents()), 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled aside {} in {}'.format(el['class'], item['url']))

    for el in soup.find_all('script'):
        el.decompose()

    for el in soup.find_all(class_=['category-tagline', 'post-authors', 'table-of-contents']):
        el.decompose()

    for el in soup.find_all('a'):
        href = el['href']
        if el.has_attr('data-analytics-module'):
            el.attrs = {}
        # https://www.businessinsider.com/reviews/out?u=https%3A%2F%2Fwww.disneyplus.com%2Fseries%2Fthats-so-raven%2F7QEGF45PWksK
        if re.search(r'insider\.com\/reviews\/out\?u=', href):
            split_url = urlsplit(el['href'])
            query = parse_qs(split_url.query)
            href = query['u'][0]
        elif href.startswith('https://affiliate.insider.com'):
            split_url = urlsplit(href)
            query = parse_qs(split_url.query)
            href = query['u'][0]
            if href.startswith('https://www.amazon.com'):
                href = utils.clean_url(href)
            elif href.startswith('https://prf.hn'):
                while href.startswith('https://prf.hn'):
                    m = re.search(r'/destination:(.*)', href)
                    if m:
                        href = unquote_plus(m.group(1))
            elif href.startswith('https://go.redirectingat.com'):
                split_url = urlsplit(href)
                query = parse_qs(split_url.query)
                href = query['url'][0]
        el['href'] = href

    for el in soup.find_all('span'):
        if el.get('class'):
            if 'rich-tooltip' in el['class']:
                el.unwrap()
        if el.get('style'):
            if re.search('font-size: 0px;', el['style']):
                el.decompose()

    for el in soup.find_all(re.compile('h\d')):
        el.attrs = {}

    for el in soup.find_all(class_=True):
        if 'headline-bold' in el['class']:
            if el.name != 'strong':
                if el.get('style'):
                    el['style'] += ' font-weight: bold;'
                else:
                    el['style'] = 'font-weight: bold;'
            del el['class']
        elif 'horizontal-scroll' in el['class']:
            del el['class']
        else:
            if re.search(r'^(ol|p|strong|table|tbody|th|tr|td|ul)$', el.name):
                del el['class']

    item['content_html'] = str(soup).replace('<p>&nbsp;</p>', '')
    return item


def get_feed(args, save_debug=False):
    split_url = urlsplit(args['url'])
    if 'feeds.' in split_url.netloc:
        return rss.get_feed(args, save_debug, get_content)

    page_json = utils.get_url_json(args['url'] + '?app-shell')
    # redirects to https://www.businessinsider.com/ajax/mobile-feed/vertical/homepage
    # https://www.businessinsider.com/ajax/mobile-feed/category/newsletter, etc.
    if not page_json:
        return None
    if save_debug:
        utils.write_file(page_json, './debug/feed.json')

    n = 0
    feed = utils.init_jsonfeed(args)
    if page_json.get('attributes'):
        feed['title'] = page_json['attributes']['label']
    feed_items = []
    for article in page_json['data']:
        url = article['links']['site']
        # Skip podcasts
        if url == 'https://link.chtbl.com/therefresh':
            logger.debug('skipping ' + url)
            continue
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed


def test_handler():
    feeds = ['https://feeds.insider.com/custom/all'
             'https://feeds.businessinsider.com/custom/all',
             'https://www.businessinsider.com/category/10-things-in-tech',
             'https://www.businessinsider.com/category/newsletter'
             'https://www.insider.com/guides']
    for url in feeds:
        get_feed({"url": url}, True)
