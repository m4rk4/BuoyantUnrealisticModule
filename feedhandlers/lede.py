import av, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    return utils.clean_url(img_src) + '?w={}&q=75'.format(width)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/all'
        query = ''
    elif 'category' in paths:
        path = split_url.path
        del paths[0]
        query = ''
        for it in paths:
            query += '&categorySlug={}'.format(it)
    elif 'author' in paths:
        path = split_url.path
        query = '&authorSlug={}'.format(paths[-1])
    else:
        path = split_url.path
        query = '&slug={}'.format(paths[-1])

    next_url = '{0}://{1}/_next/data/{2}/en/_sites/{3}{4}.json?siteSlug={3}{5}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], site_json['siteSlug'], path, query)
    #print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        m = re.search(r'"buildId":"([^"]+)"', page_html)
        if m and m.group(1) != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = m.group(1)
            utils.update_sites(url, site_json)
            next_url = '{0}://{1}/_next/data/{2}/en/_sites/{3}{4}.json?siteSlug={3}{5}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], site_json['siteSlug'], path, query)
            next_data = utils.get_url_json(next_url)
            if not next_data:
                return None
    return next_data


def format_block(block):
    block_html = ''
    if block['name'] == 'core/paragraph' or block['name'] == 'core/heading' or block['name'] == 'core/list-item':
        block_html = block['innerHTML']
    elif block['name'] == 'core/separator':
        block_html = '<hr/>'
    elif block['name'] == 'core/image' and block['tagName'] == 'figure':
        soup = BeautifulSoup(block['innerHTML'], 'html.parser')
        img_src = ''
        attr = next((it for it in block['attributes'] if it['name'] == 'srcset'), None)
        if attr and attr['value'] != 'false':
            img_src = utils.image_from_srcset(attr['value'], 1000)
        else:
            attr = next((it for it in block['attributes'] if it['name'] == 'src'), None)
            if attr and attr['value'] != 'false':
                img_src = attr['value']
            else:
                el = soup.find('img')
                if el:
                    img_src = el['src']
        if img_src:
            captions = []
            el = soup.find(class_='wp-element-caption')
            if el:
                captions.append(el.decode_contents())
            el = soup.find(class_='wp-element-credit')
            if el:
                captions.append(el.decode_contents())
            block_html = utils.add_image(img_src, ' | '.join(captions))
        else:
            logger.warning('unhandled core/image')
    elif block['name'] == 'core/video' and block['tagName'] == 'figure':
        soup = BeautifulSoup(block['innerHTML'], 'html.parser')
        el = soup.find('video')
        if el:
            video_src = el['src']
            video_type = ''
            if re.search(r'\.mp4', video_src) or re.search(r'\.mov', video_src):
                video_type = 'video/mp4'
            elif re.search(r'\.webm', video_src):
                video_type = 'video/webm'
            elif re.search(r'\.m3u8', video_src):
                video_type = 'application/x-mpegURL'
            else:
                video_container = av.open(video_src)
                if 'mp4' in video_container.format.extensions:
                    video_type = 'video/mp4'
                elif 'webm' in video_container.format.extensions:
                    video_type = 'video/webm'
                else:
                    video_type = 'application/x-mpegURL'
                video_container.close()
            if el.get('poster'):
                poster = el['poster']
            else:
                poster = ''
            captions = []
            it = soup.find(class_='wp-element-caption')
            if it:
                captions.append(it.decode_contents())
            it = soup.find(class_='wp-element-credit')
            if it:
                captions.append(it.decode_contents())
            block_html = utils.add_video(video_src, video_type, poster, ' | '.join(captions))
    elif block['name'] == 'core/embed' and block['tagName'] == 'figure':
        attr = next((it for it in block['attributes'] if it['name'] == 'url'), None)
        if attr:
            block_html = utils.add_embed(attr['value'])
        else:
            logger.warning('unhandled core/embed figure')
    elif block['name'] == 'lede/iframe':
        attr = next((it for it in block['attributes'] if it['name'] == 'src'), None)
        if attr:
            block_html = utils.add_embed(attr['value'])
        else:
            logger.warning('unhandled lede/iframe')
    elif block['name'] == 'core/quote':
        quote = ''
        for blk in block['innerBlocks']:
            quote += format_block(blk)
        block_html = utils.add_blockquote(quote)
    elif block['name'] == 'core/list':
        block_html = '<' + block['tagName']
        if block.get('attributes'):
            attr = next((it for it in block['attributes'] if it['name'] == 'start'), None)
            block_html += ' start="{}"'.format(attr['value'])
        block_html += '>'
        for blk in block['innerBlocks']:
            block_html += format_block(blk)
        block_html += '</{}>'.format(block['tagName'])
    elif block['name'] == 'lede/related-post' or block['name'] == 'lede-common/related-post':
        pass
    else:
        logger.warning('unhandled content block ' + block['name'])
    return block_html

def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    utils.write_file(next_data, './debug/debug.json')

    post_json = next_data['pageProps']['post']
    item = {}
    item['id'] = post_json['id']
    item['url'] = post_json['link']
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['dateGmt']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post_json['modifiedGmt']).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    authors = []
    for it in post_json['byline']['profiles']:
        authors.append(it['title'])
    if authors:
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if post_json.get('tags') and post_json['tags'].get('nodes'):
        item['tags'] = []
        for it in post_json['tags']['nodes']:
            item['tags'].append(it['name'])

    item['content_html'] = ''
    if post_json.get('dek'):
        item['content_html'] += '<p><em>{}</em></p>'.format(post_json['dek'])

    if post_json.get('featuredImage'):
        if post_json['featuredImage']['node'].get('srcSet'):
            item['_image'] = utils.image_from_srcset(post_json['featuredImage']['node']['srcSet'], 1000)
        else:
            item['_image'] = resize_image(post_json['featuredImage']['node']['sourceUrl'])
        captions = []
        if post_json['featuredImage']['node'].get('caption'):
            caption = re.sub(r'<p>(.*)</p>', r'\1', post_json['featuredImage']['node']['caption'].strip())
            captions.append(caption)
        if post_json['featuredImage']['node'].get('credit'):
            caption = re.sub(r'<p>(.*)</p>', r'\1', post_json['featuredImage']['node']['credit'].strip())
            captions.append(caption)
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    if post_json.get('excerpt'):
        item['summary'] = post_json['excerpt']

    for block in post_json['contentBlocks']['blocks']:
        item['content_html'] += format_block(block)

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) > 1 and 'feed' in paths:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    utils.write_file(next_data, './debug/feed.json')

    feed = utils.init_jsonfeed(args)
    n = 0
    feed_items = []
    for post in next_data['pageProps']['posts']:
        post_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, post['uri'])
        if save_debug:
            logger.debug('getting content for ' + post_url)
        item = get_content(post_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed['title'] = next_data['pageProps']['siteTitle']
    if next_data['pageProps'].get('title'):
        feed['title'] += ' | ' + next_data['pageProps']['title']

    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed