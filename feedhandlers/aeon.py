import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    elif split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    path += '.json'

    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url, site_json=site_json)
        if page_html:
            soup = BeautifulSoup(page_html, 'lxml')
            el = soup.find('script', id='__NEXT_DATA__')
            if el:
                next_data = json.loads(el.string)
                if next_data['buildId'] != site_json['buildId']:
                    logger.debug('updating {} buildId'.format(split_url.netloc))
                    site_json['buildId'] = next_data['buildId']
                    utils.update_sites(url, site_json)
                return next_data['props']
    return next_data


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    #utils.write_file(next_data, './debug/next.json')

    article_json = next_data['pageProps']['article']
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = url
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['publishedAt'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if article_json.get('updatedAt'):
        dt = datetime.fromisoformat(article_json['updatedAt'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()

    item['authors'] = []
    if article_json.get('authors'):
        for it in article_json['authors']:
            item['authors'].append({"name": it['name']})
    elif article_json.get('credits'):
        soup = BeautifulSoup(article_json['credits'].replace('\n', ', '), 'html.parser')
        for el in soup.find_all('p'):
            item['authors'].append({"name": el.get_text().strip()})
    if article_json.get('editor'):
        item['authors'].append({"name": article_json['editor']['name'] + ' (editor)'})
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = []
    if article_json.get('tags'):
        for it in article_json['tags']:
            item['tags'].append(it['title'])
    if article_json.get('topics'):
        for it in article_json['topics']:
            item['tags'].append(it['title'])
    if article_json.get('topic') and article_json['topic'] not in item['tags']:
        item['tags'].append(article_json['topic'])
    if len(item['tags']) == 0:
        del item['tags']

    if article_json.get('description'):
        item['summary'] = article_json['description']
    elif article_json.get('standfirstLong'):
        item['summary'] = article_json['standfirstLong']
    elif article_json.get('standfirstShort'):
        item['summary'] = article_json['standfirstShort']

    item['content_html'] = ''

    if article_json['type'] == 'video':
        if article_json['hoster'] == 'youtube':
            item['content_html'] += utils.add_embed('https://www.youtube.com/watch?v=' + article_json['hosterId'])
        elif article_json['hoster'] == 'vimeo':
            item['content_html'] += utils.add_embed('https://player.vimeo.com/video/' + article_json['hosterId'])
        else:
            logger.warning('unhandled video hoster {} in {}'.format(article_json['hoster'], item['url']))
        if 'embed' in args:
            return item
        if article_json.get('standfirstShort'):
            item['content_html'] += '<h2>{}</h2>'.format(article_json['standfirstShort'])
        if article_json.get('description'):
            item['content_html'] += article_json['description']
        if article_json.get('credits'):
            item['content_html'] += article_json['credits']
        return item

    if article_json.get('standfirstLong'):
        try:
            item['content_html'] += '<p><em>{}</em></p>'.format(article_json['standfirstLong'].encode('iso-8859-1').decode('utf-8'))
        except:
            item['content_html'] += '<p><em>{}</em></p>'.format(article_json['standfirstLong'])

    if article_json.get('image'):
        image = article_json['image']
    elif article_json.get('thumbnail'):
        image = article_json['thumbnail']
    elif article_json.get('imageSquare'):
        image = article_json['imageSquare']
    else:
        image = None
    if image:
        if image.get('url'):
            item['image'] = image['url']
        if image.get('urls'):
            item['image'] = image['urls']['header']
        if image.get('caption'):
            caption = re.sub(r'^<p>(.*)</p>$', r'\1', image['caption'])
        elif article_json.get('thumbnailAttribution'):
            caption = re.sub(r'^<p>(.*)</p>$', r'\1', article_json['thumbnailAttribution'])
        else:
            caption = ''
        item['content_html'] += utils.add_image(item['image'], caption)

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    body = ''
    if article_json.get('body'):
        body = article_json['body']
    elif article_json.get('section1'):
        # Sections based on psyche.co
        sections = ['Need to know', 'What to do', 'Key points', 'Learn more', 'Links & books']
        r = re.compile(r'section\d')
        for i, it in enumerate(list(filter(r.match, article_json.keys()))):
            body += '<h2>{}</h2>'.format(sections[i]) + article_json[it].encode('iso-8859-1').decode('utf-8')
    soup = BeautifulSoup(body, 'html.parser')

    for el in soup.find_all('figure'):
        new_html = ''
        if el.get('class') and 'ld-embed-block-wrapper' in el['class']:
            it = el.find('iframe')
            if it:
                new_html = utils.add_embed(it['src'])
        else:
            img = el.find('img', class_='ld-image-block')
            if img:
                it = el.find(class_='ld-image-caption')
                if it:
                    caption = it.get_text().strip()
                else:
                    caption = ''
                new_html = utils.add_image(img['src'], caption)
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled figure in ' + item['url'])

    dropcap = ''
    el = soup.find('p')
    if not el.find('span', class_='ld-dropcap'):
        if not dropcap:
            dropcap = config.dropcap_style
            new_el = soup.new_tag('style')
            new_el.string = dropcap
            el.insert_before(new_el)
        el.attrs = {}
        el['class'] = 'dropcap'
        # new_html = re.sub(r'^(<[^>]+>)(<[^>]+>)?(\W*\w)', r'\1\2<span style="float:left; font-size:4em; line-height:0.8em;">\3</span>', str(el), 1)
        # new_html += '<span style="clear:left;"></span>'
        # new_el = BeautifulSoup(new_html, 'html.parser')
        # el.replace_with(new_el)

    for el in soup.find_all('span', class_='ld-dropcap'):
        it = el.find_parent('p')
        if it:
            it.attrs = {}
            it['class'] = 'dropcap'
            if not dropcap:
                dropcap = config.dropcap_style
                new_el = soup.new_tag('style')
                new_el.string = dropcap
                it.insert_before(new_el)
            el.unwrap()
        else:
            logger.warning('unhandled ld-dropcap parent in ' + item['url'])
        # el['style'] = 'float:left; font-size:4em; line-height:0.8em;'
        # new_el = soup.new_tag('span')
        # new_el['style'] = 'clear:left;'
        # el.find_parent('p').insert_after(new_el)

    for el in soup.find_all('p', class_='pullquote'):
        new_html = utils.add_pullquote(el.decode_contents())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all('blockquote', class_=False):
        el['style'] = 'border-left: 3px solid #ccc; margin: 1.5em 10px; padding: 0.5em 10px;'

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
