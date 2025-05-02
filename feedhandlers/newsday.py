import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    # https://www.newsday.com/_next/image?url=https%3A%2F%2Fcdn.newsday.com%2Fimage-service%2Fversion%2Fc%3AYzgwMzZhMWYtOTBiZC00%3AZGNjMjRiMjUtY2Y1Yy00%2F2025_davies_march_collection.jpg%3Ff%3DFreeform%26w%3D770%26q%3D1&w=828&q=80
    return 'https://www.newsday.com/_next/image?url={0}%3Ff%3DFreeform%26w%3D{1}%26q%3D1&w={1}&q=80'.format(quote_plus(img_src), width)


def add_image(image):
    captions = []
    if image.get('caption'):
        captions.append(re.sub(r'^<p>|</p>$', '', image['caption'].strip()))
    if image.get('byline'):
        captions.append(image['byline'])
    if image.get('organization'):
        captions.append(image['organization'])
    return utils.add_image(resize_image(image['baseUrl']), ' | '.join(captions))


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
    path += '.json'
    next_url = 'https://{}/_next/data/{}{}'.format(split_url.netloc, site_json['buildId'], path)
    # print(next_url)
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
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')
    return get_item(next_data['pageProps']['data']['page']['leaf'], args, site_json, save_debug)


def get_item(page_json, args, site_json, save_debug):
    # print(page_json['id'])
    item = {}
    item['id'] = page_json['id']
    item['url'] = page_json['url']
    item['title'] = page_json['headline']

    dt = datetime.fromisoformat(page_json['publishedDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if page_json.get('updatedDate'):
        dt = datetime.fromisoformat(page_json['updatedDate'])
        item['date_modified'] = dt.isoformat()

    item['authors'] = []
    if page_json.get('authors'):
        item['authors'] = [{"name": x['name']} for x in page_json['authors']]
    elif page_json.get('byline'):
        item['authors'] = [{"name": page_json['byline']}]
    elif page_json.get('source'):
        item['authors'] = [{"name": x['name']} for x in page_json['source']]
    else:
        item['authors'] = [{"name": "Newsday"}]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = []
    if page_json.get('contentPath'):
        item['tags'] += [x['title'] for x in page_json['contentPath']]
    if page_json.get('tags'):
        item['tags'] += [x['name'] for x in page_json['tags']]
    if len(item['tags']) == 0:
        del item['tags']

    item['content_html'] = ''

    if page_json.get('topElement'):
        if page_json['topElement']['__typename'] == 'Image':
            item['image'] = resize_image(page_json['topElement']['baseUrl'])
            if page_json['__typename'] != 'Video':
                item['content_html'] += add_image(page_json['topElement'])

    if page_json['__typename'] == 'Video':
        if page_json['subType'] == 'video':
            item['content_html'] += utils.add_video(page_json['mediaLink'], 'video/mp4', item['image'], page_json['headline'], use_videojs=True)
        elif page_json['subType'] == 'sendToNews':
            item['content_html'] += utils.add_embed(page_json['embedCode'])
        else:
            logger.warning('unhandled Video subType {} in {}'.format(page_json['subType'], item['url']))
        if 'embed' not in args:
            item['content_html'] += page_json['body']
        item['summary'] = page_json['lead']
        return item

    if page_json['__typename'] == 'Article' and page_json['subType'] == 'blogPost':
        soup = BeautifulSoup(page_json['body'], 'html.parser')
        el = soup.select('p:has(> a:-soup-contains("Read more"))')
        if el:
            item['url'] = el[0].a['href']
            el[0].a['href'] = config.server + '/content?read&url=' + quote_plus(el[0].a['href'])
            item['content_html'] += str(soup)
            el[0].decompose()
            item['summary'] = str(soup)
    
    if page_json.get('lead'):
        if page_json['__typename'] != 'Video':
            item['content_html'] = '<p><em>' + page_json['lead'] + '</em></p>' + item['content_html']
        if 'summary' not in item:
            item['summary'] = page_json['lead']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if page_json['__typename'] == 'Article' and page_json['subType'] == 'blogPost':
        pass
    elif page_json.get('embeds'):
        soup = BeautifulSoup(page_json['body'], 'html.parser')
        for embed in page_json['embeds']:
            el = soup.find(attrs={"data-onecms-id": embed['id']})
            if el:
                new_html = ''
                if embed['__typename'] == 'Image':
                    new_html = add_image(embed)
                elif embed['__typename'] == 'Video' and embed['subType'] == 'video':
                    if embed.get('topElement') and embed['topElement']['__typename'] == 'Image':
                        poster = resize_image(embed['topElement']['baseUrl'])
                    else:
                        poster = ''
                    new_html = utils.add_video(embed['mediaLink'], 'video/mp4', poster, embed.get('headline'), use_videojs=True)
                elif embed['__typename'] == 'Video' and embed['subType'] == 'sendToNews':
                    new_html = utils.add_embed(embed['embedCode'])
                elif embed['__typename'] == 'Animation':
                    new_html = utils.add_video(embed['mediaLink'], 'video/mp4', '', embed.get('caption'), use_videojs=True)
                elif embed['__typename'] == 'StoryWidget' and embed.get('rawHtml'):
                    if 's2nPlayer' in embed['rawHtml']:
                        m = re.search(r'src="([^"]+)', embed['rawHtml'])
                        if m:
                            new_html = utils.add_embed(m.group(1))
                    elif 'flourish-embed' in embed['rawHtml']:
                        m = re.search(r'data-src="([^"]+)', embed['rawHtml'])
                        if m:
                            new_html = utils.add_embed('https://flo.uri.sh/' + m.group(1))
                if new_html:
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.replace_with(new_el)
                else:
                    logger.warning('unhandled embed type {} id {}'.format(embed['__typename'], embed['id']))
            else:
                logger.warning('unhandled embed type {} id {}'.format(embed['__typename'], embed['id']))
        item['content_html'] += str(soup)
    else:
        item['content_html'] += page_json['body']

    if page_json.get('newsBox'):
        item['content_html'] += utils.add_blockquote(page_json['newsBox'])

    if page_json['__typename'] == 'ImageGallery':
        item['_gallery'] = []
        item['content_html'] += '<h3><a href="{}/gallery?url={}" target="_blank">View gallery</a></h3>'.format(config.server, quote_plus(item['url']))
        item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
        for i, image in enumerate(page_json['contents']):
            img_src = resize_image(image['baseUrl'])
            thumb = resize_image(image['baseUrl'], 640)
            captions = []
            if image.get('caption'):
                captions.append(re.sub(r'^<p>|</p>$', '', image['caption'].strip()))
            if image.get('byline'):
                captions.append(image['byline'])
            if image.get('organization'):
                captions.append(image['organization'])
            caption = ' | '.join(captions)
            item['content_html'] += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img_src) + '</div>'
            item['_gallery'].append({"src": img_src, "caption": caption, "thumb": thumb})
        if i % 2 == 0:
            item['content_html'] += '<div style="flex:1; min-width:360px;">&nbsp;</div>'
        item['content_html'] += '</div>'


    if page_json['__typename'] == 'StoryGallery':
        for content in page_json['contents']:
            it = get_item(content, args, site_json, False)
            if it:
                item['content_html'] += '<hr style="margin:2em 0;"><div style="font-size:1.05em; font-weight:bold; margin-bottom:8px;">' + it['_display_date'] + '</div>'
                item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;">' + it['title'] + '</div>'
                item['content_html'] += '<div style="margin-bottom:1em;">By ' + it['author']['name'] + '</div>'
                item['content_html'] += it['content_html']

    return item


def get_feed(url, args, site_json, save_debug=False):
    if '/rss/' in url:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    def iter_slots(slots):
        articles = []
        for slot in slots:
            if slot['__typename'] == 'Slot':
                for teaser in slot['teasers']['teasers']:
                    if teaser['content']['__typename'] == 'Article' or teaser['content']['__typename'] == 'Video' or teaser['content']['__typename'] == 'ImageGallery':
                        articles.append(teaser['content'])
                    elif teaser['content']['__typename'] == 'Link':
                        continue
                    else:
                        logger.debug(teaser['content']['__typename'])
            elif slot['__typename'] == 'SlotGroup':
                articles += iter_slots(slot['slots'])
        return articles

    page_json = next_data['pageProps']['data']['page']['leaf']
    articles = iter_slots(page_json['slots'])

    n = 0
    feed_items = []
    for article in articles:
        if save_debug:
            logger.debug('getting content for ' + article['url'])
        item = get_item(article, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['title'] = page_json['seoTitle']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed