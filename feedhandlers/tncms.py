import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    return utils.clean_url(img_src + '?resize={}%2C'.format(width))


def get_content(url, args, site_json, save_debug=False):
    print(url)
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    m = re.search(r'([^_]+)_([0-91-f\-]+)\.html?', paths[-1])
    if not m:
        logger.warning('unhandled url ' + url)
        return None
    article_type = m.group(1)
    article_id = m.group(2)
    titles = []
    if len(paths) > 1:
        titles.append(re.sub(r'\-+', ' ', paths[-2]))

    soup = None
    ld_json = None
    tn_json = None
    page_html = utils.get_url_html(url)
    if page_html:
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('meta', attrs={"property": "og:title"})
        if el:
            titles.insert(0, el['content'])
        el = soup.find('script', attrs={"type": "application/ld+json"})
        if el:
            ld_json = json.loads(el.string)
            if save_debug:
                utils.write_file(ld_json, './debug/ld_json.json')
        el = soup.find('script', attrs={"type": "text/javascript"}, string=re.compile(r'dl\.push'))
        if el:
            m = re.search(r'dl\.push\(({"townnews":.*?})\);', el.string)
            if m:
                tn_json = json.loads(m.group(1))
                if save_debug:
                    utils.write_file(tn_json, './debug/townnews.json')

    article_json = None
    for title in titles:
        if 'collection' in args:
            n = args['collection']
        else:
            n = 5
        search_url = '{}://{}/search/?f=json&t={}&l={}&sort=date&k=&b=&sd=desc&q={}'.format(split_url.scheme, split_url.netloc, article_type, n, quote_plus(title))
        print(search_url)
        search_json = utils.get_url_json(search_url)
        if not search_json:
            continue
        for it in search_json['rows']:
            if it['uuid'] == article_id:
                article_json = it
                break
        if article_json:
            break

    if not article_json:
        if save_debug:
            utils.write_file(search_json, './debug/debug.json')

        if article_type == 'image' and tn_json:
            item = {}
            item['id'] = tn_json['asset_id']
            item['url'] = tn_json['asset_canonical']
            item['title'] = tn_json['asset_headline']
            dt = datetime.fromisoformat(tn_json['articlePublishTime']).astimezone(timezone.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)
            if tn_json.get('articleUpdateTime'):
                dt = datetime.fromisoformat(tn_json['articleUpdateTime']).astimezone(timezone.utc)
                item['date_modified'] = dt.isoformat()
            item['author'] = {"name": tn_json['asset_byline']}
            el = soup.find(id='asset-content')
            if el:
                it = el.find('img')
                if it:
                    if it.get('data-srcset'):
                        item['_image'] = utils.image_from_srcset(it['data-srcset'], 1200)
                    else:
                        item['_image'] = it['src']
                    captions = []
                    it = el.find(class_='caption-text')
                    if it:
                        captions.append(re.sub('\s*<p>(.*)</p>\s*$', r'\1', it.decode_contents()))
                    it = el.find(class_='tnt-byline')
                    if it:
                        captions.append(it.decode_contents())
                    item['content_html'] = utils.add_image(item['_image'], ' | '.join(captions))
                else:
                    logger.warning('unhandled asset-content in ' + item['url'])
                return item
        else:
            logger.warning('unable to find article for ' + url)
        return None

    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['uuid']
    item['url'] = article_json['url']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['starttime']['iso8601']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json['lastupdated'].get('iso8601'):
        dt = datetime.fromisoformat(article_json['lastupdated']['iso8601']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if article_json.get('authors'):
        authors = []
        for it in article_json['authors']:
            authors.append(it['screen_name'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif article_json.get('byline'):
        item['author']['name'] = re.sub(r'^By ', '', article_json['byline'], flags=re.I)
    elif tn_json and tn_json.get('asset_byline'):
        item['author']['name'] = tn_json['asset_byline']
    elif ld_json and ld_json.get('creator'):
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(ld_json['creator']))
    else:
        item['author']['name'] = split_url.netloc

    if article_json.get('keywords'):
        item['tags'] = article_json['keywords'].copy()

    item['content_html'] = ''

    if article_json.get('subheadline'):
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['subheadline'])
        item['summary'] = article_json['subheadline']

    lede_img = ''
    gallery = ''
    if article_json['type'] != 'image' and article_json['type'] != 'collection':
        if soup:
            if article_json['type'] == 'html':
                content = soup.find(class_='html-content')
                el = content.find('iframe')
                if el:
                    item['content_html'] += utils.add_embed(el['src'])
                else:
                    item['content_html'] += '<blockquote><b>Unknown embedded content in <a href="{0}">{0}</a></b></blockquote>'.format(item['url'])
                    logger.warning('unhandled html content in ' + item['url'])

            if article_json['type'] == 'video':
                el = soup.find(attrs={"data-asset-uuid": item['id']})
            else:
                el = soup.find(id='asset-video-primary')
            if el:
                # https://lancasteronline.com/sports/highschool/baseball/l-l-spring-sports-roundtable-2023-dont-look-now-but-playoff-push-is-on-around/article_11e57042-df73-11ed-b9c0-5b61d37c0a43.html
                it = el.find('script', attrs={"src": True})
                if it:
                    player_html = utils.get_url_html(it['src'])
                    if player_html:
                        m = re.search(r'"m3u8"\s?:\s?"([^"]+)"', player_html)
                        if m:
                            video_src = m.group(1)
                        m = re.search(r'"thumb"\s?:\s?"([^"]+)"', player_html)
                        if m:
                            poster = m.group(1)
                        captions = []
                        m = re.search(r'"title"\s?:\s?"([^"]+)"', player_html)
                        if m:
                            captions.append(m.group(1))
                        m = re.search(r'"description"\s?:\s?"([^"]+)"', player_html)
                        if m:
                            captions.append(m.group(1))
                        lede_img = utils.add_video(video_src, 'application/x-mpegURL', poster, ' | '.join(captions))
                else:
                    it = el.find('iframe')
                    if it:
                        lede_img = utils.add_embed(it['src'])
                    else:
                        logger.warning('unhandled asset-video-primary in ' + item['url'])

            el = soup.find(id='asset-photo-carousel')
            if el:
                gallery = '<h2>Photo gallery</h2>'
                for i, photo in enumerate(el.find_all(class_=re.compile(r'^photo-[0-9a-f]{8}'))):
                    it = photo.find('img')
                    if it:
                        if it.get('data-src'):
                            img_src = resize_image(it['data-src'])
                        else:
                            img_src = resize_image(it['src'])
                        captions = []
                        it = photo.find(class_='caption-text')
                        if it:
                            captions.append(re.sub('^<p>(.*)</p>$', r'\1', it.decode_contents()))
                        it = photo.find(class_='tnt-byline')
                        if it:
                            captions.append(it.decode_contents())
                        if i == 0:
                            lede_img += utils.add_image(img_src, ' | '.join(captions))
                        gallery += utils.add_image(img_src, ' | '.join(captions))

            el = soup.find(class_='asset-photo')
            if el:
                it = el.find('img')
                if it:
                    img_uuid = list(filter(None, urlsplit(it['src']).path[1:].split('/')))[-2]
                    embed_item = get_content('{}://{}/image_{}.html'.format(split_url.scheme, split_url.netloc, img_uuid), {"embed": True}, site_json, False)
                    if embed_item:
                        lede_img = embed_item['content_html']

    if article_json.get('preview') and article_json['preview'].get('url'):
        item['_image'] = resize_image(article_json['preview']['url'])
        if not lede_img and article_json['type'] != 'image' and article_json['type'] != 'collection':
            embed_item = get_content('{}://{}/image_{}.html'.format(split_url.scheme, split_url.netloc, article_json['preview']['uuid']), {"embed": True}, site_json, False)
            if embed_item:
                lede_img += embed_item['content_html']
            else:
                lede_img += utils.add_image(item['_image'])

    content_html = ''
    for content in article_json['content']:
        m = re.search(r'<iframe .*?src="([^"]+)"', content)
        if m:
            content_html += utils.add_embed(m.group(1))
            continue
        if content.startswith('<figure'):
            if re.search(r'inline-editorial-(html|image|video)', content):
                m = re.search(r'href="([^"]+)"', content)
                if m:
                    embed_item = get_content(m.group(1), {"embed": True}, site_json, False)
                    content_html += embed_item['content_html']
                    continue
            elif re.search(r'inline-editorial-collection', content):
                m = re.search(r'href="([^"]+)"', content)
                if m:
                    embed_item = get_content(m.group(1), {"embed": True}, site_json, False)
                    link = '{}/content?read&url={}'.format(config.server, quote_plus(embed_item['url']))
                    content_html += utils.add_image(embed_item['_image'], 'Photo gallery: <a href="{}">{}</a>'.format(embed_item['url'], embed_item['title']), link=link)
                    continue
            elif re.search(r'inline-editorial-article', content):
                # Generally related articles
                continue
        elif content.startswith('<aside'):
            if re.search(r'tncms-inline-relcontent', content):
                content_html += utils.add_blockquote(re.sub(r'^<aside [^>]+>(.*)</aside>$', r'\1', content))
                continue
        content_html += content

    if article_json['type'] == 'collection':
        n = len(article_json['items'])
        for it in article_json['items']:
            collection_item = get_content(it['url'], {"collection": n}, site_json, False)
            content_html += collection_item['content_html']

    content_html = content_html.strip()

    if article_json['type'] == 'image':
        captions = []
        if 'embed' in args and content_html:
            content_html = content_html.replace('</p><p>', ' ')
            content_html = content_html.replace('<p>', '')
            content_html = content_html.replace('</p>', '')
            captions.append(content_html)
        if article_json.get('authors'):
            for it in article_json['authors']:
                captions.append(it['byline'])
        else:
            captions.append(item['author']['name'])
        item['content_html'] += utils.add_image(resize_image(article_json['resource_url']), ' | '.join(captions))

    if lede_img and not content_html.startswith('<figure'):
        item['content_html'] += lede_img

    if content_html and 'embed' in args:
        if article_json['type'] != 'image':
            item['content_html'] += utils.add_blockquote(content_html)
    else:
        item['content_html'] += content_html

    if gallery:
        item['content_html'] += re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', gallery)
    return item


def get_feed(url, args, site_json, save_debug=False):
    if re.search(r'f=rss', url):
        return rss.get_feed(url, args, site_json, save_debug, get_content)
    split_url = urlsplit(url)
    page_html = utils.get_url_html('{}://{}/tncms/sitemap/news.xml'.format(split_url.scheme, split_url.netloc))
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/feed.xml')

    soup = BeautifulSoup(page_html, 'lxml')

    n = 0
    feed_items = []
    for el in soup.find_all('url'):
        if save_debug:
            logger.debug('getting content for ' + el.loc.string)
        item = get_content(el.loc.string, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    #feed['title'] = soup.title.get_text()
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed