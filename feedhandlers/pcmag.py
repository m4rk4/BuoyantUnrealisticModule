import json, re
from bs4 import BeautifulSoup
from datetime import datetime

import utils

import logging

logger = logging.getLogger(__name__)


def get_image_src(el_img, width=1000, height=''):
    if el_img.has_attr('data-lazy-sized'):
        img_src = el_img['data-image-loader']
    else:
        img_src = el_img['src']

    if img_src.startswith('https://i.pcmag.com/imagery'):
        m = re.search(r'\.(size_\d+x\d+)', img_src)
        if m:
            return img_src.replace(m.group(1), 'size_{}x{}'.format(width, height))
        m = re.search(r'\.(fit_\w+)', img_src)
        if m:
            return img_src.replace(m.group(1), 'fit_lim.size_{}x{}'.format(width, height))
        m = re.search(r'\.(jpg|png)', img_src)
        if m:
            return img_src.replace(m.group(1), 'fit_lim.size_{}x{}.{}'.format(width, height, m.group(1)))
    elif el_img.has_attr('srcset'):
        return utils.image_from_srcset(el_img['srcset'], width)
    return img_src


def get_content(url, args, site_json, save_debug=False):
    article_html = utils.get_url_html(url)
    if not article_html:
        return None
    if save_debug:
        utils.write_file(article_html, './debug/debug.html')

    ld_json = None
    soup = BeautifulSoup(article_html, 'html.parser')
    for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
        ld_json = json.loads(el.string)
        if ld_json.get('@type'):
            if ld_json['@type'] == 'Article' or ld_json['@type'] == 'NewsArticle':
                break
            elif ld_json['@type'] == 'Product' and ld_json.get('review'):
                ld_json = ld_json['review']
                break
        ld_json = None
    if not ld_json:
        logger.warning('unable to find ld+json in ' + url)
        return None
    if save_debug:
        utils.write_file(ld_json, './debug/debug.json')

    item = {}
    item['id'] = url
    item['url'] = url
    item['title'] = ld_json['headline']

    dt = datetime.fromisoformat(ld_json['datePublished'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if ld_json.get('dateModified'):
        dt = datetime.fromisoformat(ld_json['dateModified'])
        item['date_modified'] = dt.isoformat()

    # Check age
    if 'age' in args:
        if not utils.check_age(item, args):
            return None

    if ld_json.get('author'):
        item['author'] = {}
        if isinstance(ld_json['author'], list):
            authors = []
            for author in ld_json['author']:
                authors.append(author['name'])
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
        else:
            item['author']['name'] = ld_json['author']['name']
    else:
        el = soup.find('a', attrs={"data-module": "author-byline"})
        if el:
            item['author'] = {}
            item['author']['name'] = el.get_text()

    m = re.search(r'PogoConfig = (\{[^\}]+\})', article_html)
    if m:
        pogo = json.loads(m.group(1))
        item['tags'] = []
        if pogo.get('category'):
            item['tags'].append(pogo['category'])
        if pogo.get('tags'):
            for tag in pogo['tags']:
                item['tags'].append(tag)

    if ld_json.get('image'):
        item['_image'] = ld_json['image'][0]['url']
    else:
        el = soup.find('meta', attrs={"property": "og:image"})
        if el:
            item['_image'] = el['content']

    if ld_json.get('description'):
        item['summary'] = ld_json['description']
    else:
        el = soup.find('meta', attrs={"property": "description"})
        if el:
            item['summary'] = el['content']

    article = soup.find('article')
    if not article:
        return item

    article.attrs = {}

    for el in article.find_all('p'):
        for it in el.find_all('strong'):
            if it.a and it.a['href'] == 'https://www.pcmag.com/newsletter_manage':
                el.decompose()
                break

    for el in article.find_all('img'):
        img_src = get_image_src(el)
        caption = ''
        for it in el.next_siblings:
            if not it.name:
                continue
            break
        if it.name == 'div' and it.small:
            caption = it.get_text().strip()
            it.decompose()
        new_el = BeautifulSoup(utils.add_image(img_src, caption), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in article.find_all('blockquote'):
        if el.has_attr('class') and 'twitter-tweet' in el['class']:
            new_el = BeautifulSoup(utils.add_embed(el.a['href']), 'html.parser')
            el.insert_before(new_el)
            el.decompose()

    for el in article.find_all('ins'):
        el.decompose()

    if save_debug:
        utils.write_file(str(article), './debug/debug.html')

    for el in article.children:
        # print('\nchild')
        # print(el.name)
        if el.name == 'div':
            if el.has_attr('x-data'):
                el.decompose()
            elif el.has_attr('id') and ('comments' in el['id'] or 'similar-products' in el['id']):
                el.decompose()
            elif el.has_attr('class') and 'review-card' in el['class']:
                el.decompose()
            elif el.h3 and re.search(r'Recommended by Our Editors', el.h3.get_text(), flags=re.I):
                el.decompose()
            elif el.find(class_=re.compile(r'hide-')) or el.find(class_=re.compile(r'commerce-')):
                el.decompose()
            elif el.find('iframe'):
                it = el.find('iframe')
                new_html = utils.add_embed(it['src'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_before(new_el)
                el.decompose()
            elif el.find(id=re.compile(r'video-container-')):
                new_html = ''
                for it in el.parent.find_all('script'):
                    m = re.search(r'window\.videoEmbeds\.push\(\{.*data:\s(\{.*\}).*\}\);', str(it), flags=re.S)
                    if m:
                        video_json = json.loads(m.group(1))
                        break
                if video_json:
                    if save_debug:
                        utils.write_file(video_json, './debug/video.json')
                    videos = []
                    for video_src in video_json['transcoded_urls']:
                        m = re.search(r'\/(\d+)\.mp4', video_src)
                        if m:
                            video = {}
                            video['src'] = video_src
                            video['height'] = m.group(1)
                    if videos:
                        video_src = utils.closest_dict(videos, '480')
                        if video_src:
                            new_html = utils.add_video(video_src, 'video/mp4', video_json['thumbnail_url'], video_json['title'])
                if new_html:
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.insert_before(new_el)
                    el.decompose()
                else:
                    logger.warning('unhandled video-container in ' + item['url'])
        elif el.name == 'section':
            if el.find(attrs={"data-parent-group": "author-bio"}):
                el.decompose()

    if '/reviews/' in url:
        review_html = ''
        el = soup.find(ref='gallery')
        if el:
            img_src = get_image_src(el.img)
        review_html += utils.add_image(img_src)

        if ld_json.get('reviewRating'):
            review_html += '<center><h3>{} / {}'.format(ld_json['reviewRating']['ratingValue'],
                                                        ld_json['reviewRating']['bestRating'])
            el = soup.find('header', id='content-header')
            if el:
                if el.img and el.img.has_attr('alt') and 'editors choice' in el.img['alt']:
                    review_html += ' 	&ndash; Editors\' Choice'
            review_html += '</h3></center>'

        el = soup.find(class_='bottom-line')
        if el:
            review_html += '<h3>{}</h3>{}'.format(el.h3.get_text(), el.p)

        el = soup.find(class_='pros-cons')
        if el:
            headers = el.find_all('h3')
            for i, ul in enumerate(el.find_all('ul')):
                review_html += '<h3>{}</h3><ul>'.format(headers[i].get_text())
                for li in ul.find_all('li'):
                    review_html += '<li>{}</li>'.format(li.get_text())
                review_html += '</ul>'

        el = soup.find(id='specs')
        if el:
            review_html += '<h3>{}</h3>'.format(el.get_text())
            for it in el.next_siblings:
                if it.name == None:
                    continue
                break
            if it.name == 'table':
                it.attrs = {}
                for t in it.find_all(['tr', 'td']):
                    t.attrs = {}
                review_html += str(it)

        if review_html:
            review_html += '<hr />'
            new_el = BeautifulSoup(review_html, 'html.parser')
            article.insert(0, new_el)

    item['content_html'] = ''
    if item.get('summary'):
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    el = soup.find(class_='article-image')
    if el:
        img_src = get_image_src(el.img)
        if el.small:
            caption = el.small.get_text().strip()
        else:
            caption = ''
            for it in article.children:
                if it.name:
                    if it.name == 'center':
                        caption = it.get_text().strip()
                        it.decompose()
                    break
        for it in article.children:
            if it.name:
                if it.name == 'br':
                    it.decompose()
                else:
                    break
        item['content_html'] += utils.add_image(img_src, caption)

    item['content_html'] += re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', article.decode_contents())
    item['content_html'] = re.sub(r'<hr/>\s*<hr/>', '<hr/>', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(args['url'])
    if not page_html:
        return None
    if save_debug:
        with open('./debug/debug.html', 'w', encoding='utf-8') as f:
            f.write(page_html)

    soup = BeautifulSoup(page_html, 'html.parser')

    n = 0
    items = []
    feed = utils.init_jsonfeed(args)
    if '/reviews' in args['url']:
        links = soup.find_all('a', attrs={"data-element": "review-title"})
    else:
        links = soup.find_all('a', attrs={"data-element": "article-title"})
    for a in links:
        url = a['href']
        if not url.startswith('https://www.pcmag.com/'):
            url = 'https://www.pcmag.com' + a['href']
        if save_debug:
            logger.debug('getting content from ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed['items'] = items.copy()
    return feed
