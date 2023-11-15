import json, re
import dateutil.parser
from bs4 import BeautifulSoup, Comment
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def render_content(blocks):
    content_html = ''
    for block in blocks:
        if block['name'] == 'core/paragraph':
            # TODO check block['attributes']['dropCap']
            content_html += '<p>' + block['attributes']['content'] + '</p>'
        elif block['name'] == 'core/heading':
            content_html += '<h{0}>{1}</h{0}>'.format(block['attributes']['level'], block['attributes']['content'])
        elif block['name'] == 'core/image':
            captions = []
            if block['attributes'].get('caption'):
                captions.append(block['attributes']['caption'])
            if block['attributes'].get('credit'):
                captions.append(block['attributes']['credit'])
            content_html += utils.add_image(block['attributes']['url'], ' | '.join(captions), link=block['attributes'].get('href'))
        elif block['name'] == 'core/gallery':
            content_html += render_content(block['innerBlocks'])
        elif block['name'] == 'history/video':
            # TODO: to get video src, need to sign request
            # https://github.com/ytdl-org/youtube-dl/blob/master/youtube_dl/extractor/theplatform.py
            # https://link.theplatform.com/s/xc6n8B/media/HnpniLEkL8xv?restriction=33206&embedded=true&sdk=PDK+6.4.12&schema=2.0&switch=hls_med_fastly&assetTypes=medium_video_s3&manifest=m3u&formats=MPEG-DASH+widevine,M3U+appleHlsEncryption,M3U+none,MPEG-DASH+none,MPEG4,MP3&format=SMIL&vpaid=script&tracking=true&metr=1023&policy=144537452&csid=history.desktop.video&caid=287006&nw=171213&asnw=171213&ssnw=171213&prof=171213%3AAETN_web_live&adobe_id=55205189764115529710752165611362538282&_fw_ae=nonauthenticated&_fw_vcid2=4609292640389286&_fw_us_privacy=1---&resolution=1015,571&sig=006544045ef7ffb9cd731790effe267368484e510c87510146533130425058484d6c62
            video_json = utils.get_url_json(block['attributes']['publicUrl'] + '?format=preview')
            if video_json:
                # utils.write_file(video_json, './debug/video.json')
                poster = '{}/image?url={}&width=1200&overlay=video'.format(config.server, quote_plus(block['attributes']['poster']))
                caption = 'Watch: <a href="{}">{}</a>'.format(video_json['AETN$siteUrl']['href'], block['attributes']['title'])
                content_html += utils.add_image(poster, caption, link=video_json['AETN$siteUrl']['href'])
            else:
                logger.warning('unable to get video preview info from ' + block['attributes']['publicUrl'])
        elif block['name'] == 'core/list':
            if block['attributes']['ordered'] == True:
                tag = 'ol'
            else:
                tag = 'ul'
            content_html += '<{0}>{1}</{0}>'.format(tag, render_content(block['innerBlocks']))
        elif block['name'] == 'core/list-item':
            content_html += '<li>' + block['attributes']['content'] + '</li>'
        elif block['name'] == 'core/pullquote':
            content_html += utils.add_pullquote(block['attributes']['value'], block['attributes']['citation'])
        elif block['name'] == 'history/intro':
            content_html += render_content(block['innerBlocks']) + '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
        elif block['name'] == 'corpnews-blocks/featured-content' or block['name'] == 'corpnews-blocks/banner' or block['name'] == 'corpnews-blocks/story-grid' or block['name'] == 'corpnews-blocks/subhead' or block['name'] == 'history/table-of-contents':
            pass
        else:
            logger.warning('unhandled content block ' + block['name'])
    return content_html


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    elif split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    next_url = '{}{}/en/{}.json'.format(site_json['next_data_path'], site_json['buildId'], path)
    #print(next_url)
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

    post_json = next_data['pageProps']['post']

    item = {}
    item['id'] = post_json['id']
    item['url'] = post_json['link']
    item['title'] = post_json['title']['rendered']

    dt = datetime.fromisoformat(post_json['date_gmt']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post_json['modified_gmt']).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    if post_json.get('story_byline'):
        authors = []
        for id in post_json['story_byline']:
            author = next((it for it in next_data['pageProps']['terms'] if it['id'] == id), None)
            if author:
                authors.append(author['name'])
        if authors:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    for it in next_data['pageProps']['terms']:
        if it['taxonomy'] == 'story_category':
            item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''

    if post_json.get('excerpt'):
        item['summary'] = post_json['excerpt']['rendered']
        item['content_html'] += '<p><em>{}</em></p>'.format(post_json['excerpt']['rendered'])

    if post_json.get('featured_media'):
        image = next_data['pageProps']['images'][str(post_json['featured_media'])]
        item['_image'] = image['source_url']
        caption = ''
        captions = []
        if image['caption'].get('rendered'):
            caption = image['caption']['rendered']
            captions.append(caption)
        if image['meta'].get('credit') and image['meta']['credit'] not in caption:
            captions.append(image['meta']['credit'])
        item['content_html'] += utils.add_image(image['source_url'], ' | '.join(captions))

    if post_json['article_type_meta'] == 'Videos':
        video_json = utils.get_url_json(post_json['meta']['video_public_url'] + '?format=preview')
        if video_json:
            # utils.write_file(video_json, './debug/video.json')
            poster = '{}/image?url={}&width=1200&overlay=video'.format(config.server, quote_plus(post_json['meta']['video_poster']))
            caption = 'Watch: <a href="{}">{}</a>'.format(video_json['AETN$siteUrl']['href'], post_json['meta']['video_title'])
            item['content_html'] = utils.add_image(poster, caption, link=video_json['AETN$siteUrl']['href'])
        else:
            logger.warning('unable to get video preview info from ' + block['attributes']['publicUrl'])

    item['content_html'] += render_content(post_json['content']['blocks'])
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    n = 0
    feed_items = []
    if next_data['pageProps'].get('featuredPost'):
        if save_debug:
            logger.debug('getting content for ' + next_data['pageProps']['featuredPost']['link'])
        item = get_content(next_data['pageProps']['featuredPost']['link'], args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1

    if next_data['pageProps'].get('posts'):
        for post in next_data['pageProps']['posts']:
            if save_debug:
                logger.debug('getting content for ' + post['link'])
            item = get_content(post['link'], args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break

    if next_data['pageProps'].get('featuredStories') and next_data['pageProps']['featuredStories'].get('posts'):
        for post in next_data['pageProps']['featuredStories']['posts']:
            if save_debug:
                logger.debug('getting content for ' + post['link'])
            item = get_content(post['link'], args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break

    if next_data['pageProps'].get('stories') and next_data['pageProps']['stories'].get('posts'):
        for post in next_data['pageProps']['stories']['posts']:
            if save_debug:
                logger.debug('getting content for ' + post['link'])
            item = get_content(post['link'], args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break

    if next_data['pageProps'].get('topics') and next_data['pageProps']['topics'].get('posts'):
        for post in next_data['pageProps']['topics']['posts']:
            if save_debug:
                logger.debug('getting content for ' + post['link'])
            item = get_content(post['link'], args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break

    if next_data['pageProps'].get('videos') and next_data['pageProps']['videos'].get('posts'):
        for post in next_data['pageProps']['videos']['posts']:
            if save_debug:
                logger.debug('getting content for ' + post['link'])
            item = get_content(post['link'], args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break

    if next_data['pageProps'].get('thisDayInHistory') and next_data['pageProps']['thisDayInHistory'].get('posts'):
        for post in next_data['pageProps']['thisDayInHistory']['posts']:
            if save_debug:
                logger.debug('getting content for ' + post['link'])
            item = get_content(post['link'], args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break

    feed = utils.init_jsonfeed(args)
    if next_data['pageProps'].get('seoPost'):
        feed['title'] = next_data['pageProps']['seoPost']['yoast_head_json']['title']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed

