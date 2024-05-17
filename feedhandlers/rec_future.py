import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from markdown2 import markdown
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    split_url = urlsplit(img_src)
    return '{}://{}{}?auto=webp&optimize=high&quality=70&width={}'.format(split_url.scheme, split_url.netloc, split_url.path, width)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if site_json.get('locale'):
        path = '/' + site_json['locale']
    else:
        path = ''
    if len(paths) == 0:
        path += '/index'
    elif split_url.path.endswith('/'):
        path += split_url.path[:-1]
    else:
        path += split_url.path
    path += '.json'

    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
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
    utils.write_file(next_data, './debug/next.json')

    item = {}
    if next_data['pageProps']['page']['data'][0]['attributes'].get('article'):
        article_data = next_data['pageProps']['page']['data'][0]['attributes']['article']['data']['attributes']
        item['id'] = next_data['pageProps']['page']['data'][0]['attributes']['article']['data']['id']
    elif next_data['pageProps']['page']['data'][0]['attributes'].get('resource'):
        article_data = next_data['pageProps']['page']['data'][0]['attributes']['resource']['data']['attributes']
        item['id'] = next_data['pageProps']['page']['data'][0]['attributes']['resource']['data']['id']
    if save_debug:
        utils.write_file(article_data, './debug/debug.json')

    split_url = urlsplit(url)
    item['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, next_data['pageProps']['page']['data'][0]['attributes']['slug'])

    item['title'] = article_data['title']

    dt = datetime.fromisoformat(article_data['publishedAt'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    dt = datetime.fromisoformat(article_data['updatedAt'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if article_data.get('editor'):
        item['author']['name'] = article_data['editor']['data']['attributes']['name']
    elif article_data.get('newsAndResearchResource') and article_data['newsAndResearchResource'].get('author'):
        item['author']['name'] = article_data['newsAndResearchResource']['author']
    else:
        item['author']['name'] = split_url.netloc

    item['tags'] = []
    if article_data.get('categories'):
        for it in article_data['categories']['data']:
            item['tags'].append(it['attributes']['name'])
    if article_data.get('tags'):
        for it in article_data['tags']['data']:
            item['tags'].append(it['attributes']['name'])
    if article_data.get('countryTags'):
        for it in article_data['countryTags']['data']:
            item['tags'].append(it['attributes']['name'])
    if article_data.get('industryTags'):
        for it in article_data['industryTags']['data']:
            item['tags'].append(it['attributes']['name'])
    if article_data.get('threatTags'):
        for it in article_data['threatTags']['data']:
            item['tags'].append(it['attributes']['name'])
    if article_data.get('topicTags'):
        for it in article_data['topicTags']['data']:
            item['tags'].append(it['attributes']['name'])

    item['content_html'] = ''

    lede_image = None
    if article_data.get('image'):
        lede_image = article_data['image']
    elif article_data.get('headerImage'):
        lede_image = article_data['headerImage']
    if lede_image:
        image_data = lede_image['desktop']['data']['attributes']
        item['_image'] = '{}{}?w=1080'.format(site_json['image_cms'], image_data['url'])
        item['content_html'] += utils.add_image(item['_image'], lede_image.get('caption'))

    body_html = ''
    if article_data.get('body') and article_data['body'].startswith('{'):
        body_json = json.loads(article_data['body'])
        if save_debug:
            utils.write_file(body_json, './debug/body.json')
        if body_json.get('blocks'):
            for block in body_json['blocks']:
                if block['type'] == 'paragraph':
                    item['content_html'] += '<p>' + block['data']['text'] + '</p>'
                elif block['type'] == 'header':
                    item['content_html'] += '<h{0}>{1}</h{0}>'.format(block['data']['level'], block['data']['text'])
                elif block['type'] == 'raw':
                    raw_soup = BeautifulSoup(block['data']['html'], 'html.parser')
                    if raw_soup.find('blockquote', class_='twitter-tweet'):
                        links = raw_soup.find_all('a')
                        item['content_html'] += utils.add_embed(links[-1]['href'])
                    else:
                        logger.warning('unhandled raw block in ' + item['url'])
                else:
                    logger.warning('unhandled block type {} in {}'.format(block['type'], item['url']))
            return item

    if article_data.get('body'):
        body_html = markdown(article_data['body'])
    elif article_data.get('blocks'):
        for it in article_data['blocks']:
            if it.get('text'):
                body_html += markdown(it['text'])

    soup = BeautifulSoup(body_html, 'html.parser')
    for el in soup.find_all('table'):
        if el.get('style'):
            el['style'] += 'width:100%;'
        else:
            el['style'] = 'width:100%;'

    for el in soup.find_all('code'):
        new_html = '<pre style="padding:0.5em; white-space:pre; overflow-x:auto; background:#F2F2F2;">{}</pre>'.format(str(el))
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('p'):
        img = el.find('img')
        if img:
            img_src = img['src'] + '?w=1080'
            if img_src.startswith('/'):
                img_src = site_json['image_cms'] + img_src
            caption = el.get_text().strip()
            if caption.startswith('_'):
                caption = caption[1:]
            new_html = utils.add_image(img_src, caption)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all('blockquote', class_='twitter-tweet'):
        links = el.find_all('a')
        new_html = utils.add_embed(links[-1]['href'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('iframe', class_='wistia_embed'):
        new_html = ''
        wistia_html = utils.get_url_html(el['src'])
        if wistia_html:
            m = re.search(r'W\.iframeInit\((.*)\);\n', wistia_html)
            if m:
                wistia_json = json.loads('[{}]'.format(m.group(1)))
                utils.write_file(wistia_json, './debug/video.json')
                video = next((it for it in wistia_json[0]['assets'] if it['type'] == 'iphone_video'), None)
                if video:
                    caption = 'Watch: ' + wistia_json[0]['name']
                    if wistia_json[0].get('seoDescription'):

                        caption += '. ' + re.sub(r'^<p>(.*)</p>$', r'\1', markdown(wistia_json[0]['seoDescription']))
                    if wistia_json[0].get('embed_options') and wistia_json[0]['embed_options'].get('stillUrl'):
                        poster = wistia_json[0]['embed_options']['stillUrl']
                    else:
                        poster = ''
                    new_html = utils.add_video(video['url'], 'video/mp4', poster, caption)
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            it = el.find_parent(class_='wistia_responsive_padding')
            if it:
                it.insert_after(new_el)
                it.decompose()
            else:
                el.insert_after(new_el)
                el.decompose()
        else:
            logger.warning('unhandled wistia embed in ' + item['url'])

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
