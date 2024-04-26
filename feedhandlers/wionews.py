import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    query = ''
    if len(paths) == 0:
        path = '/index'
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
        if len(paths) > 1:
            query = '?subsection=' + paths[1]
    path += '.json'
    next_url = '{}://{}/_next/data/{}{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, query)
    print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if not el:
            logger.warning('unable to find __NEXT_DATA__ in ' + url)
            return None
        next_data = json.loads(el.string)
        if next_data['buildId'] != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = next_data['buildId']
            utils.update_sites(url, site_json)
        return next_data['props']
    return next_data


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) > 0 and paths[-1] == 'embed':
        args['embed'] = True
        del paths[-1]
        page_url = '{}://{}/{}'.format(split_url.scheme, split_url.netloc, '/'.join(paths))
    else:
        page_url = url
    next_data = get_next_data(page_url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    if next_data['pageProps']['schema'][0].get('newsarticle'):
        news_article = next_data['pageProps']['schema'][0]['newsarticle'][0]
    elif next_data['pageProps']['schema'][0].get('news_schema'):
        news_article = next_data['pageProps']['schema'][0]['news_schema'][0]

    item = {}
    item['url'] = news_article['mainEntityOfPage']['@id']
    item['title'] = news_article['headline']

    dt = datetime.fromisoformat(news_article['datePublished'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(news_article['dateModified'])
    item['date_modified'] = dt.isoformat()

    authors = []
    authors.append(news_article['author']['name'])
    if next_data['pageProps'].get('authordetail'):
        for author in next_data['pageProps']['authordetail']:
            if not any([True if author['name'].lower() in it.lower() else False for it in authors]):
                authors.append('{} {}'.format(author['title'], author['name']))
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if news_article.get('keywords'):
        item['tags'] = [it.strip() for it in news_article['keywords'].split(',')]

    if news_article.get('description'):
        item['summary'] = news_article['description']

    if next_data['pageProps']['sectionName'] == 'videoDetails':
        detail_json = next_data['pageProps']['videodetail']
    elif next_data['pageProps']['sectionName'] == 'photoDetails':
        detail_json = next_data['pageProps']['photodetail']
    else:
        detail_json = next_data['pageProps']['newsdetail']

    item['id'] = detail_json['id']

    if detail_json.get('thumbnail_url'):
        if detail_json['thumbnail_url'].startswith('//'):
            item['_image'] = 'https:' + detail_json['thumbnail_url']
        else:
            item['_image'] = detail_json['thumbnail_url']

    if detail_json['news_type'] == 'video':
        captions = []
        captions.append(detail_json['title'])
        if detail_json.get('source'):
            captions.append(detail_json['source'])
        item['content_html'] = utils.add_video(detail_json['videourl'], 'application/x-mpegURL', item['_image'], ' | '.join(captions))
        if 'embed' in args:
            return item

    if 'embed' in args:
        item['content_html'] = '<div style="width:80%; margin-right:auto; margin-left:auto; border:1px solid black; border-radius:10px;">'
        if item.get('_image'):
            item['content_html'] += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(item['url'], item['_image'])
        item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(split_url.netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        item['content_html'] += '<p><a href="{}/content?read&url={}">Read</a></p></div></div>'.format(config.server, quote_plus(item['url']))
        return item

    item['content_html'] = ''
    if detail_json.get('highlights'):
        item['content_html'] += re.sub(r'^(<p>&nbsp;</p>)?\s*<p>(.*)</p>$', r'<p><em>\2</em></p>', detail_json['highlights'].strip())

    if detail_json.get('thumbnail_url'):
        captions = []
        if detail_json.get('thumbnail_caption'):
            captions.append(detail_json['thumbnail_caption'])
        if detail_json.get('thumbnail_source'):
            captions.append(detail_json['thumbnail_source'])
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    if detail_json.get('content'):
        if detail_json['content'].startswith('<'):
            soup = BeautifulSoup(detail_json['content'], 'html.parser')
            for el in soup.find_all('img'):
                if el['src'].startswith('//'):
                    img_src = 'https:' + el['src']
                else:
                    img_src = el['src']
                caption = ''
                if el.parent and el.parent.name == 'p':
                    it = el.parent.find_next_sibling()
                    if it and it.name == 'p' and it.contents[0].name == 'em':
                        caption = it.em.decode_contents()
                        it.decompose()
                    new_el = BeautifulSoup(utils.add_image(img_src, caption), 'html.parser')
                    el.parent.insert_after(new_el)
                    el.decompose()
                else:
                    new_el = BeautifulSoup(utils.add_image(img_src, caption), 'html.parser')
                    el.replace_with(new_el)

            for el in soup.find_all(class_='videoWrapper'):
                it = el.find('iframe')
                if it:
                    new_html = utils.add_embed(it['src'])
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.replace_with(new_el)
                else:
                    logger.warning('unhandled videoWrapper in ' + item['url'])

            for el in soup.find_all(class_='twitter-tweet'):
                links = el.find_all('a')
                new_html = utils.add_embed(links[-1]['href'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)

            for el in soup.find_all('blockquote', class_='instagram-media'):
                new_html = utils.add_embed(el['data-instgrm-permalink'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)

            for el in soup.find_all('iframe'):
                new_html = utils.add_embed(el['src'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                if el.parent and el.parent.name == 'p':
                    el.parent.replace_with(new_el)
                else:
                    el.replace_with(new_el)

            for el in soup.find_all(class_=['ui-state-default', 'twitter-block']):
                el.unwrap()

            for el in soup.find_all(class_='close-mark'):
                el.decompose()

            for el in soup.select('p:has(> strong:-soup-contains("Also read:"))'):
                el.decompose()

            for el in soup.select('p:-soup-contains("Also read:")'):
                el.decompose()

            item['content_html'] += str(soup)
        else:
            item['content_html'] += '<p>' + detail_json['content'] + '</p>'

    if detail_json['news_type'] == 'Photogallery':
        for photo in next_data['pageProps']['details']['photoGallery']:
            if photo.get('gallerySource'):
                caption = 'Photograph: ' + photo['gallerySource']
            else:
                caption = ''
            desc = ''
            if photo.get('galleryTitle'):
                desc += '<h3>' + photo['galleryTitle'] + '</h3>'
            if photo.get('galleryContent'):
                desc += photo['galleryContent']
            item['content_html'] += '<div>&nbsp;</div><hr style="width:80%; margin:auto;"/><div>&nbsp;</div>' + utils.add_image(photo['galleryImage'], caption, desc=desc)

    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    n = 0
    feed_items = []
    for article in next_data['pageProps']['news']:
        if save_debug:
            logger.debug('getting content for ' + article['websiteurl'])
        item = get_content(article['websiteurl'], args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    # feed['title'] =
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
