import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit, quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_image_src(image_ref, image_netloc, aspect='o', size='lg'):
    # aspect can be 4by3, 16by9, 1by1
    # orig is invalid but seems to defaults to the original image dimensions
    # size = xs, sm, md, lg, xl
    if aspect == 'auto':
        aspect = 'o'
    m = re.search(r'^([^_]+)_([^_]+)_(\d{4})(\d\d)(\d\d)_([0-9a-f]+)', image_ref.split(':')[-1])
    if not m:
        return ''
    return 'https://{}/{}/{}/{}/{}/{}/{}/{}_{}.{}'.format(image_netloc, m.group(1), m.group(6)[0:2], aspect, m.group(3), m.group(4), m.group(5), m.group(6), size, m.group(2))


def add_gallery(gallery_ref, image_netloc, link_preview=True):
    ref_split = gallery_ref.split(':')
    gallery_url = 'https://www.{}.com/_/gallery/{}/images'.format(ref_split[0], ref_split[-1])
    if ref_split[0] == 'toofab':
        gallery_url += '/1'
    gallery_json = utils.get_url_json(gallery_url)
    if not gallery_json:
        return ''
    if link_preview:
        for key, val in gallery_json['derefs'].items():
            key_split = key.split(':')
            if 'gallery' in key_split:
                gallery_link = 'https://www.{}.com/photos/{}'.format(key_split[0], val['slug'])
                heading = '<div style="font-size:1.2em; font-weight:bold;">Photos: <a href="{}">{}</a></div>'.format(gallery_link, val['title'])
                link = '{}/content?read&url={}'.format(config.server, quote_plus(gallery_link))
                return utils.add_image(get_image_src(val['image_ref'], image_netloc), '', link=link, heading=heading)
        logger.warning('unhandled gallery preview')

    gallery_html = ''
    for image in gallery_json['message']['nodes']:
        captions = []
        if image.get('description'):
            captions.append(image['description'])
        if image.get('credit'):
            captions.append(image['credit'])
        gallery_html += utils.add_image(get_image_src(image['_id'], image_netloc), ' | '.join(captions))
    return gallery_html


def add_video(block, image_netloc, page_soup):
    ref_split = block['node_ref'].split(':')
    video_json = utils.get_url_json('https://www.{}.com/_/video/{}/'.format(ref_split[0], ref_split[-1]))
    if video_json:
        if video_json['message'].get('kaltura_mp4_url'):
            return utils.add_video(video_json['message']['kaltura_mp4_url'], 'video/mp4', get_image_src(video_json['message']['image_ref'], image_netloc, '16by9'), video_json['message']['title'])
        elif video_json['message'].get('mezzanine_url'):
            return utils.add_video(video_json['message']['mezzanine_url'], 'application/x-mpegURL', get_image_src(video_json['message']['image_ref'], image_netloc, '16by9'), video_json['message']['title'])
        else:
            logger.warning('unsupported video ' + video_ref)
            return ''
    # Look for Youtube video
    el = page_soup.find('section', id=re.compile(block['etag']))
    if el:
        it = el.find('script', string=re.compile(r'renderYoutubeVideoBlock'))
        if it:
            m = re.search(r"cueVideoById\('([^']+)'", it.string)
            if m:
                return utils.add_embed('https://www.youtube.com/watch?v=' + m.group(1))
    return ''


def get_content(url, args, site_json, save_debug):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')
    soup = BeautifulSoup(page_html, 'lxml')

    m = re.search(r'node: ({.+?}),\n', page_html)
    if not m:
        logger.warning('unable to find node content in ' + url)
        return None

    node = json.loads(m.group(1))
    if save_debug:
        utils.write_file(node, './debug/debug.json')

    item = {}
    item['id'] = node['_id']

    if ':gallery:' in node['_schema']:
        item['url'] = '{}://{}/photos/{}'.format(split_url.scheme, split_url.netloc, node['slug'])
    else:
        item['url'] = '{}://{}/{}'.format(split_url.scheme, split_url.netloc, node['slug'])
    item['title'] = node['title']

    dt = datetime.fromisoformat(node['published_at'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(node['order_date'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    el = soup.find('span', class_='article__author')
    if el:
        item['author'] = {"name": re.sub(r'^By ', '', el.get_text(), flags=re.I)}
    else:
        item['author'] = {"name": site_json['author']}

    item['tags'] = []
    m = re.search(r'derefs: ({.+?}),\n', page_html)
    if m:
        derefs = json.loads(m.group(1))
        for key, val in derefs.items():
            if re.search(r'category|channel|person', key):
                item['tags'].append(val['title'])
    else:
        logger.warning('unable to find derefs content in ' + url)
    if node.get('hashtags'):
        for val in node['hashtags']:
            item['tags'].append(val)
    if not item.get('tags'):
        del item['tags']

    item['_image'] = get_image_src(node['image_ref'], site_json['image_netloc'])

    if node.get('meta_description'):
        item['summary'] = node['meta_description']

    item['content_html'] = ''
    if ':gallery:' in node['_schema']:
        schema_split = node['_schema'].split(':')
        item['content_html'] = add_gallery('{}:gallery:{}'.format(schema_split[1], node['_id']), site_json['image_netloc'], False)

    if node.get('hf'):
        for i, hf in enumerate(node['hf']):
            if node['hf_styles'][i] == 'uppercase':
                hf_text = hf.upper()
            elif node['hf_styles'][i] == 'lowercase':
                hf_text = hf.lower()
            elif node['hf_styles'][i] == 'titlecase':
                hf_text = hf.title()
            elif node['hf_styles'][i] == 'none':
                hf_text = hf
            else:
                logger.warning('unhandled hf_styles {} in {}'.format(node['hf_styles'][i], item['url']))
                hf_text = hf
            item['content_html'] += '<h{0}>{1}</h{0}>'.format(node['hf_sizes'][i], hf_text)

    if node.get('blocks'):
        for block in node['blocks']:
            if 'block:text-block' in block['_schema']:
                item['content_html'] += block['text']
            elif 'block:heading-block' in block['_schema']:
                item['content_html'] += '<h3>{}</h3>'.format(block['text'])
            elif 'block:image-block' in block['_schema']:
                item['content_html'] += utils.add_image(get_image_src(block['node_ref'], site_json['image_netloc'], block['aspect_ratio']))
            elif 'block:gallery-block' in block['_schema']:
                item['content_html'] += add_gallery(block['node_ref'], site_json['image_netloc'])
            elif 'block:video-block' in block['_schema']:
                item['content_html'] += add_video(block, site_json['image_netloc'], soup)
            elif 'block:youtube-video-block' in block['_schema']:
                item['content_html'] += utils.add_embed('https://www.youtube.com/watch?v={}'.format(block['id']))
            elif 'block:twitter-tweet-block' in block['_schema']:
                twitter_url = utils.get_twitter_url(block['tweet_id'])
                if twitter_url:
                    item['content_html'] += utils.add_embed(twitter_url)
                else:
                    item['content_html'] += '<blockquote>{}</blockquote>'.format(block['tweet_text'])
            elif 'block:instagram-media-block' in block['_schema']:
                item['content_html'] += utils.add_embed('https://www.instagram.com/p/{}/'.format(block['id']))
            elif 'block:facebook-post-block' in block['_schema']:
                item['content_html'] += utils.add_embed(block['href'])
            elif 'block:divider-block' in block['_schema']:
                item['content_html'] += '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
            elif 'block:code-block' in block['_schema']:
                code = BeautifulSoup(block['code'], 'html.parser')
                if code.iframe:
                    item['content_html'] += utils.add_embed(code.iframe['src'])
                else:
                    logger.warning('unhandled block {} in {}'.format(block['_schema'], item['url']))
            elif 'block:iframe-block' in block['_schema']:
                if not re.search(r'minigames\.versusgame\.com', block['src']):
                    item['content_html'] += utils.add_embed(block['src'])
            elif 'block:article-block' in block['_schema']:
                # Related articles
                continue
            else:
                logger.warning('unhandled block {} in {}'.format(block['_schema'], item['url']))

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    if 'rss' in url:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    articles = None
    page_html = utils.get_url_html(args['url'])
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')
    soup = BeautifulSoup(page_html, 'lxml')

    el = soup.find('script', string=re.compile(r'"pbj:tmz:news:node:article:1-0-1"'))
    if el:
        m = re.search(r'\s+({"tmz:article:.+?})\n', el.string)
        if m:
            articles = json.loads(m.group(1))
    if not articles:
        logger.warning('unable to locate articles in ' + args['url'])
        return None
    if save_debug:
        utils.write_file(articles, './debug/feed.json')

    split_url = urlsplit(args['url'])
    n = 0
    items = []
    for key, article in articles.items():
        if ':article:' not in key:
            continue
        url = '{}://{}/{}'.format(split_url.scheme, split_url.netloc, article['slug'])
        # Check age
        if args.get('age'):
            item = {}
            dt = datetime.fromtimestamp(article['created_at']/1000000).replace(tzinfo=timezone.utc)
            item['_timestamp'] = dt.timestamp()
            if not utils.check_age(item, args):
                if save_debug:
                    logger.debug('skipping old article ' + url)
                continue
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
    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
