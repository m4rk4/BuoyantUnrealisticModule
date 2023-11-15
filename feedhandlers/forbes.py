import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import utils
from feedhandlers import brightcove, rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_wheels_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    wp_url = 'https://www.forbes.com/wheels/wp-json/web-stories/v1/web-story?slug={}'.format(paths[-1])
    post_json = utils.get_url_json(wp_url)
    if not post_json:
        logger.warning('error getting data from ' + wp_url)
        return None
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')
    return wp_posts.get_post_content(post_json[0], args, site_json, save_debug)


def get_video_content(url, args, site_json, save_debug=False):
    m = re.search(r'/video/(\d+)/', url)
    if not m:
        logger.warning('unable to determine video id in ' + url)
        return None
    bc_url = 'https://players.brightcove.net/2097119709001/60dyn27d5_default/index.html?videoId={}'.format(m.group(1))
    item = brightcove.get_content(bc_url, {}, {}, save_debug)
    if item:
        item['url'] = utils.clean_url(url)
    return item


def get_gallery_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    m = re.search(r'window\["forbes"\]\["simple-site"\] = ({.*})</script>', page_html)
    if not m:
        logger.warning('unable to find simple-site data in ' + url)
        return None
    page_json = json.loads(m.group(1))
    if save_debug:
        utils.write_file(page_json, './debug/debug.json')

    m = re.search(r'window\.FbsCarouselConfig\[[^\]]+\] = ({.*});\s</script>', page_html)
    if not m:
        logger.warning('unable to find FbsCarouselConfig in ' + url)
        return None
    gallery_json = json.loads(m.group(1))
    if save_debug:
        utils.write_file(gallery_json, './debug/gallery.json')

    item = {}
    item['id'] = page_json['gallery']['id']
    item['url'] = page_json['gallery']['url']
    item['title'] = page_json['gallery']['title']

    date = '{}T{}:00:00'.format(page_json['tracking']['publishDate'], page_json['tracking']['publishHour'])
    dt_loc = datetime.fromisoformat(date)
    tz_loc = pytz.timezone('US/Eastern')
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    date = '{}T{}:00:00'.format(page_json['tracking']['updateDate'], page_json['tracking']['updateHour'])
    dt_loc = datetime.fromisoformat(date)
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {"name": page_json['tracking']['authorName']}

    item['tags'] = []
    if page_json['tracking'].get('primaryChannel'):
        item['tags'].append(page_json['tracking']['primaryChannel'])
    if page_json['tracking'].get('primarySection'):
        item['tags'].append(page_json['tracking']['primarySection'])

    item['_image'] = page_json['gallery']['image']

    item['content_html'] = ''
    n = page_json['gallery']['length']
    for slide in gallery_json['slides']:
        if slide['scope']['title'] == 'Advertisement':
            continue
        item['content_html'] += utils.add_image(slide['scope']['image'], slide['scope'].get('credit'))
        item['content_html'] += '<h3>{}</h3>{}'.format(slide['scope']['title'], slide['scope']['caption'])
        n = n - 1
        if n > 0:
            item['content_html'] += '<hr style="width:80%; margin-left:auto; margin-right:auto;"/><br/>'

    return item


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if split_url.path.startswith('/pictures/'):
        return get_gallery_content(url, args, site_json, save_debug)
    elif split_url.path.startswith('/video/'):
        return get_video_content(url, args, site_json, save_debug)
    elif split_url.path.startswith('/wheels/'):
        return get_wheels_content(url, args, site_json, save_debug)

    api_url = 'https://www.forbes.com{}?malcolm=A&api=true&streamIndex=1'.format(split_url.path)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    article_json = api_json['article']
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['articleId']
    item['url'] = article_json['uri']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['date'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    authors = []
    authors.append(article_json['authorGroup']['primaryAuthor']['name'])
    if article_json['authorGroup'].get('coAuthors'):
        for it in article_json['authorGroup']['coAuthors']:
            authors.append(it['name'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if article_json.get('channelSectionMappings'):
        for it in article_json['channelSectionMappings']:
            if it.get('channelName') and it['channelName'] not in item['tags']:
                item['tags'].append(it['channelName'])
            if it.get('sectionName') and it['sectionName'] not in item['tags']:
                item['tags'].append(it['sectionName'])
    if article_json.get('newsKeywords'):
        for it in article_json['newsKeywords']:
            if it not in item['tags']:
                item['tags'].append(it)
    if not item.get('tags'):
        del item['tags']

    if article_json.get('image'):
        item['_image'] = article_json['image']

    item['summary'] = article_json['description']

    soup = BeautifulSoup(article_json['body'], 'html.parser')

    item['content_html'] = ''

    el = soup.find()
    if el.name == 'h4' and el.sub:
        item['content_html'] += utils.add_image(item['_image'], el.sub.get_text())
        el.decompose()
    elif article_json.get('heroMedia') and el.get('class') and 'embed-base' not in el['class']:
        if article_json['heroMedia']['type'] == 'image':
            captions = []
            if article_json['heroMedia'].get('caption') and article_json['heroMedia']['caption'].strip():
                captions.append(article_json['heroMedia']['caption'])
            if article_json['heroMedia'].get('credit'):
                captions.append(article_json['heroMedia']['credit'])
            item['content_html'] += utils.add_image(article_json['heroMedia']['imgSrc'], ' | '.join(captions))
        elif article_json['heroMedia']['type'] == 'brightcove':
            # account # in https://i.forbesimg.com/simple-site/dist/js/common-b8322888b02027f14cfb.js
            # https://edge.api.brightcove.com/playback/v1/accounts/2097119709001/videos/6307211614112
            item['content_html'] += utils.add_embed('https://players.brightcove.net/2097119709001/{}_default/index.html?videoId={}'.format(article_json['heroMedia']['playerId'], article_json['heroMedia']['videoId']))

    for el in soup.find_all('fbs-ad'):
        el.decompose()

    for el in soup.find_all('script'):
        if (el.get('class') and 'fbs-cnx' in el['class']) or re.search(r'connatix\.com', el.string):
            el.decompose()
        else:
            logger.warning('unhandled scrip in ' + item['url'])

    for el in soup.find_all(class_=re.compile(r'article_paragraph_2|halfway_hardwall_|newsletter_container|recirc-module|topline-heading')):
        el.decompose()

    for el in soup.find_all(class_='vestpocket'):
        el.decompose()
        if article_json.get('showNoVestPocket'):
            logger.warning('unhandled vestpocket in ' + item['url'])

    for el in soup.find_all(class_=re.compile(r'subhead\d?-embed')):
        text = el.get_text().strip().lower()
        if el.name == 'h4':
            print(text)
            if text.startswith('by'):
                if all([True if it.lower() in text else False for it in authors]):
                    el.decompose()
            elif 'more from forbes' in text:
                for it in el.find_next_siblings('a', class_='link-embed'):
                    it.decompose()
                el.decompose()
        elif text == 'Topline':
            el.decompose()
        elif text == '':
            el.decompose()
        else:
            el.attrs = {}

    for el in soup.find_all('abbr', class_='drop-cap'):
        el.attrs = {}
        el.name = 'span'
        el['style'] = 'float:left; font-size:4em; line-height:0.8em;'
        new_html = '<span style="float:clear;"></span>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.find_parent('p').insert_after(new_el)

    for el in soup.find_all(class_='key-facts'):
        new_html = '<ul>'
        for it in el.find_all(class_='key-facts-element'):
            new_html += '<li>{}</li>'.format(it.decode_contents())
        new_html += '</ul>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('hr', class_='rule-embed'):
        if el.next_sibling and el.next_sibling.name == 'hr':
            el.decompose()
        el.attrs = {}
        el['style'] = 'width:80%; margin-left:auto; margin-right:auto;'

    for embed in article_json['embedData']:
        el = soup.find(class_='embed-{}'.format(embed['id']))
        if el:
            new_html = ''
            if embed['type'] == 'image' or embed['type'] == 'toplineImage':
                captions = []
                if embed['data'].get('caption') and embed['data']['caption'].strip():
                    captions.append(embed['data']['caption'])
                if embed['data'].get('credit'):
                    captions.append(embed['data']['credit'])
                if embed['data'].get('cropX1'):
                    img_src = 'https://specials-images.forbesimg.com/imageserve/{}/{}x{}.jpg?cropX1={}&cropX2={}&cropY1={}&cropY2={}'.format(
                        embed['data']['guid'], embed['data']['cropWidth'], embed['data']['cropHeight'],
                        embed['data']['cropX1'], embed['data']['cropX2'], embed['data']['cropY1'],
                        embed['data']['cropY2'])
                elif embed['data'].get('cropWidth'):
                    img_src = 'https://specials-images.forbesimg.com/imageserve/{}/{}x{}.jpg?fit=scale'.format(
                        embed['data']['guid'], embed['data']['cropWidth'], embed['data']['cropHeight'])
                else:
                    img_src = 'https://specials-images.forbesimg.com/imageserve/{}/960x0.jpg?fit=scale'.format(
                        embed['data']['guid'])
                new_html = utils.add_image(img_src, ' | '.join(captions))

            elif embed['type'] == 'link':
                new_html = '<ul><li><a href="{}">{}</a></li></ul>'.format(embed['data']['url'], embed['data']['title'])

            elif embed['type'] == 'quote':
                new_html = utils.add_pullquote(embed['data']['html'], embed['data'].get('credit'))

            elif embed['type'] == 'findsModule':
                captions = []
                if embed['data'].get('caption') and embed['data']['caption'].strip():
                    captions.append(embed['data']['caption'])
                if embed['data'].get('credit'):
                    captions.append(embed['data']['credit'])
                new_html = '<div style="width:90%; margin-left:auto; margin-right:auto; padding:8px; border:1px solid black;">{}<h3>{}</h3><p><a href="{}">{}</a><br/>'.format(
                    utils.add_image(embed['data']['url'], ' | '.join(captions)), embed['data']['title'],
                    embed['data']['findsNonAffiliateLink'], embed['data']['findsLabel'])
                if embed['data'].get('salePrice'):
                    new_html += '<b>${}</b> <strike>${}</strike> {}'.format(embed['data']['salePrice'], embed['data']['price'], embed['data']['callOutText'])
                else:
                    new_html += '<b>${}<b>'.format(embed['data']['price'])
                new_html += '</p></div>' + embed['data']['description']

            elif embed['type'] == 'gallery':
                caption = '<a href="{}">View gallery</a>: {}'.format(embed['gallery']['uri'], embed['gallery']['title'])
                new_html += utils.add_image(embed['gallery']['slides'][0]['image'], caption, link=embed['gallery']['uri'])

            else:
                logger.warning('unhandled embed type {} in {}'.format(embed['type'], item['url']))

            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()

    for el in soup.find_all(class_='embedly-align'):
        new_html = ''
        it = el.find('fbs-embedly')
        if it:
            split_url = urlsplit(it['iframe-src'])
            query = parse_qs(split_url.query.replace('&amp;', '&'))
            if query.get('src'):
                new_html += utils.add_embed(query['src'][0])
            elif query.get('url'):
                new_html += utils.add_embed(query['url'][0])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled embedly embed in ' + item['url'])

    for el in soup.find_all('a'):
        href = el['href']
        el.attrs = {}
        el['href'] = href

    item['content_html'] += re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', str(soup))
    item['content_html'] = item['content_html'].replace('</ul><ul>', '')
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(args, site_json, save_debug, get_content)


def test_handler():
    feeds = ['https://www.forbes.com/real-time/feed2'
             'https://www.forbes.com/innovation/feed']
    for url in feeds:
        get_feed({"url": url}, True)
