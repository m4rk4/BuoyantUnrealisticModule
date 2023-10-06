import json, pytz, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_video_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')
    soup = BeautifulSoup(page_html, 'lxml')

    item = {}
    el = soup.find('meta', attrs={"property": "og:url"})
    if el:
        item['id'] = el['content']
        item['url'] = el['content']

    el = soup.find('meta', attrs={"property": "og:title"})
    if el:
        item['title'] = el['content']

    el = soup.find('meta', attrs={"property": "og:image"})
    if el:
        item['_image'] = el['content']

    el = soup.find('meta', attrs={"property": "og:description"})
    if el:
        item['summary'] = el['content']

    el = soup.find('link', attrs={"type": "application/smil+xml"})
    if el:
        item['_video'] = utils.get_redirect_url(el['href'])
        if re.search(r'\.mp4', item['_video'], flags=re.I):
            video_type = 'video/mp4'
        else:
            video_type = 'application/x-mpegURL'

    if not item.get('_video'):
        return None

    caption = '<a href="{}">{}</a>'.format(item['url'], item['title'])
    item['content_html'] = utils.add_video(item['_video'], video_type, item['_image'], caption)
    return item


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'html.parser')

    meta = {}
    for el in soup.find_all('meta'):
        if el.get('property'):
            key = el['property']
        elif el.get('name'):
            key = el['name']
        else:
            continue
        if meta.get(key):
            if isinstance(meta[key], str):
                if meta[key] != el['content']:
                    val = meta[key]
                    meta[key] = []
                    meta[key].append(val)
            if el['content'] not in meta[key]:
                meta[key].append(el['content'])
        else:
            meta[key] = el['content']
    if save_debug:
        utils.write_file(meta, './debug/meta.json')

    el = soup.find('script', attrs={"type": "application/ld+json"})
    if el:
        ld_json = json.loads(el.string)
        if save_debug:
            utils.write_file(ld_json, './debug/debug.json')
        item = {}
        if ld_json.get('identifier'):
            item['id'] = ld_json['identifier']
        else:
            item['id'] = urlsplit(url).path

        item['url'] = ld_json['url']

        if ld_json.get('headline'):
            item['title'] = ld_json['headline']

        dt = dateutil.parser.parse(ld_json['datePublished'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        dt = dateutil.parser.parse(ld_json['dateModified'])
        item['date_modified'] = dt.isoformat()

        authors = []
        if ld_json.get('author'):
            for it in ld_json['author']:
                authors.append(it['name'])
        elif ld_json.get('publisher'):
            authors.append(ld_json['publisher']['name'])
        if authors:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

        if meta.get('article:tag'):
            if isinstance(meta['article:tag'], list):
                item['tags'] = meta['article:tag'].copy()
            else:
                item['tags'] = []
                item['tags'].append(meta['article:tag'])

        if ld_json.get('image'):
            item['_image'] = ld_json['image'][0]['url']

        if ld_json.get('description'):
            item['summary'] = ld_json['description']

        if '/watch/' in item['url'] and ld_json.get('video'):
            video = ld_json['video'][0]
            item['title'] = video['name']
            item['_image'] = video['thumbnailUrl']
            if 'MPEG4' in video['contentUrl']:
                video_type = 'video/mp4'
            else:
                video_type = 'application/x-mpegURL'
            item['content_html'] = utils.add_video(video['contentUrl'], video_type, video['thumbnailUrl'], video['name'])
            if video.get('description'):
                item['content_html'] += '<p>{}</p>'.format(video['description'])
            return item
    else:
        item = {}
        if meta.get('brightspot.contentId'):
            item['id'] = meta['brightspot.contentId']
        else:
            item['id'] = urlsplit(url).path

        item['url'] = meta['og:url']
        item['title'] = meta['og:title']

        dt = datetime.fromisoformat(meta['article:published_time']).replace(tzinfo=timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        dt = datetime.fromisoformat(meta['article:modified_time']).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()

        if meta.get('article:author'):
            if meta['article:author'].startswith('https'):
                el = soup.find('a', href=meta['article:author'])
                if el:
                    item['author'] = {"name": el.get_text()}
            else:
                item['author'] = {"name": meta['article:author']}

        if meta.get('article:tag'):
            if isinstance(meta['article:tag'], list):
                item['tags'] = meta['article:tag'].copy()
            else:
                item['tags'] = []
                item['tags'].append(meta['article:tag'])

        if meta.get('og:image'):
            item['_image'] = meta['og:image']

    item['content_html'] = ''
    lead = soup.find(class_='ArticlePage-lead')
    if lead:
        if lead.find(class_='VideoLead'):
            el = lead.find(class_='jwplayer')
            if el:
                if el.get('data-mp4'):
                    item['content_html'] += utils.add_video(el['data-mp4'], 'video/mp4', el.get('data-poster'))
                elif el.get('data-hls'):
                    item['content_html'] += utils.add_video(el['data-hls'], 'application/x-mpegURL', el.get('data-poster'))
            else:
                logger.warning('unhandled VideoLead in ' + item['url'])
        else:
            el = lead.find('img')
            if el:
                captions = []
                it = lead.find(class_='Figure-credit')
                if it:
                    captions.append(it.get_text())
                it = lead.find(class_='Figure-credit')
                if it:
                    captions.append(it.get_text())
                item['content_html'] += utils.add_image(el['src'], ' | '.join(captions))
            else:
                logger.warning('unhandled ArticlePage-lead in ' + item['url'])

    body = soup.find(class_='ArticlePage-articleBody')
    if body:
        if save_debug:
            utils.write_file(str(body), './debug/debug.html')

        for el in body.find_all(id=re.compile(r'taboola')):
            el.decompose()

        for el in body.find_all('script'):
            el.decompose()

        for el in body.find_all(class_='ArticlePage-branding'):
            el.decompose()

        for el in body.find_all(class_=['RichTextBody', 'ArticlePage-articleBody-items', 'ListicleItem', 'ListicleItem-titleWrap']):
            el.unwrap()

        for el in body.find_all(class_='ListicleItem-anchor'):
            el.name = 'hr'
            el.attrs = {}

        for el in body.find_all(class_='Enhancement'):
            new_html = ''
            if el.find(class_='twitter-tweet'):
                links = el.find_all('a')
                new_html = utils.add_embed(links[-1]['href'])
            elif el.find('figure', class_='Figure'):
                captions = []
                it = el.find(class_='Figure-credit')
                if it:
                    captions.append(it.get_text())
                it = el.find(class_='Figure-credit')
                if it:
                    captions.append(it.get_text())
                it = el.find('img')
                if it:
                    if it.get('width') and it.get('height'):
                        if int(it['height']) > int(it['width']) and it.get('srcset'):
                            img_src = utils.image_from_srcset(it['srcset'], 1200)
                        else:
                            img_src = it['src']
                    new_html = utils.add_image(img_src, ' | '.join(captions))
            elif el.find(class_='SimpleCastPlayer'):
                it = el.find('iframe')
                new_html = utils.add_embed(it['src'])
            elif el.find(class_='PagePromo'):
                el.decompose()
                continue
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled Enhancement in ' + item['url'])

        for el in body.find_all(class_='VideoEnhancement'):
            new_html = ''
            it = lead.find(class_='jwplayer')
            if it:
                if it.get('data-mp4'):
                    new_html = utils.add_video(it['data-mp4'], 'video/mp4', it.get('data-poster'))
                elif it.get('data-hls'):
                    new_html = utils.add_video(it['data-hls'], 'application/x-mpegURL', it.get('data-poster'))
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled VideoEnhancement in ' + item['url'])

        for el in body.find_all(class_='PullQuote'):
            quote = el.find(class_='PullQuote-text')
            it = el.find(class_='PullQuote-attribution-text')
            if it:
                author = it.get_text().strip()
            else:
                author = ''
            new_html = utils.add_pullquote(quote.get_text(), author)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in body.find_all(class_='cms-textAlign-center'):
            el['style'] = 'text-align:center;'
            del el['class']

        item['content_html'] += body.decode_contents()
        item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')
    soup = BeautifulSoup(page_html, 'lxml')

    articles = []
    for el in soup.select('.PagePromo-title > a.Link'):
        if 'www.nbcsports.com' in el['href'] and ('/news/' in el['href'] or '/watch/' in el['href']):
            if el['href'] not in articles:
                articles.append(el['href'])

    n = 0
    feed_items = []
    for article in articles:
        if save_debug:
            logger.debug('getting content for ' + article)
        item = get_content(article, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
