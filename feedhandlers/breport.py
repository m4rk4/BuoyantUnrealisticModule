import json, math, re
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)

def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    if split_url.netloc == 'img.bleacherreport.net':
        m = re.search(r'w=(\d+)', split_url.query)
        if m:
            w = int(m.group(1))
        m = re.search(r'h=(\d+)', split_url.query)
        if m:
            h = int(m.group(1))
        height = math.floor(h * width / w)
        img_src = 'https://img.bleacherreport.net{}?w={}&h={}&q=75'.format(split_url.path, width, height)
    elif split_url.netloc == 'media.bleacherreport.com':
        # https://cloudinary.com/documentation/image_transformations
        paths = split_url.path.split('/')
        img_src = 'https://media.bleacherreport.com/image/upload/w_{},c_fill/{}/{}'.format(width, paths[-2], paths[-1])
    return img_src

def format_element(element):
    content_html = ''
    if element.get('content_type'):
        if element['content_type'] == 'paragraph':
            content_html += '<p>{}</p>'.format(element['content']['html'])

        elif element['content_type'] == 'div':
            content_html += '<div>{}</div>'.format(element['content']['html'])

        elif element['content_type'] == 'image':
            captions = []
            if element['content'].get('caption'):
                captions.append(element['content']['caption'])
            if element['content'].get('credit'):
                captions.append(element['content']['credit'])
            content_html += utils.add_image(resize_image(element['content']['url']), ' | '.join(captions))

        elif element['content_type'] == 'youtube':
            content_html += utils.add_embed('https://www.youtube.com/watch?v=' + element['content']['metadata']['video_id'])

        elif element['content_type'] == 'tweet':
            content_html += utils.add_embed(element['url'])

        elif element['content_type'] == 'iframe':
            content_html += utils.add_embed(element['content']['src'])

        elif element['content_type'] == 'blockquote':
            content_html += utils.add_blockquote(element['content']['html'])

        elif element['content_type'] == 'quote_indent':
            content_html += utils.add_pullquote(element['content']['html'])

        elif element['content_type'] == 'slide':
            content_html += '<h3>{}</h3>'.format(element['title'])
            for slide in element['elements']:
                content_html += format_element(slide)

        elif element['content_type'] == 'ul' or element['content_type'] == 'ol':
            content_html += '<{}>'.format(element['content_type'])
            for it in element['content']['items']:
                content_html += '<li>{}</li>'.format(it)
            content_html += '</{}>'.format(element['content_type'])

        elif element['content_type'] == 'hr':
            content_html += '<hr/>'

        elif element['content_type'] == 'hr_transparent':
            content_html += '<hr style="margin:20px auto; height:1em; color:hsla(0,0%,100%,0); opacity:0;" />'

        elif element['content_type'] == 'ad':
            pass

        else:
            logger.warning('unhandled element with content_type ' + element['content_type'])

    elif element.get('type'):
        if element['type'] == 'media slot':
            pass
        else:
            logger.warning('unhandled element with type ' + element['type'])

    else:
        logger.warning('unhandled element with no content_type or type')

    return content_html


def get_user_post(url, args, save_debug=False):
    post_html = utils.get_url_html(url)
    if not post_html:
        return None
    m = re.search(r'<!--\s+window\.INITIAL_STORE_STATE = ({.+?});\s+-->', post_html)
    if not m:
        logger.warning('unable to parse INITIAL_STORE_STATE data from ' + url)
        return None
    state_json = json.loads(m.group(1))
    if save_debug:
        utils.write_file(state_json, './debug/debug.json')

    item = {}
    item['id'] = state_json['page']['id']
    item['url'] = state_json['user_post']['shareUrl']
    item['title'] = state_json['user_post']['content']['description']
    if len(item['title']) > 50:
        m = re.search(r'^([\w\W\d\D\s]{50}[^\s]*)', item['title'], flags=re.S | re.U)
        item['title'] = m.group(1) + '...'

    dt = datetime.fromisoformat(state_json['user_post']['inserted_at'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": state_json['user_post']['authorInfo']['username']}

    item['summary'] = state_json['user_post']['content']['description']

    if state_json['user_post']['authorInfo'].get('photo_url'):
        avatar = '{}/image?url={}&height=48&mask=ellipse'.format(config.server, quote_plus(state_json['user_post']['authorInfo']['photo_url']))
    else:
        avatar = '{}/image?width=48&height=48&mask=ellipse'.format(config.server)

    item['content_html'] = '<div style="width:488px; padding:8px 0 8px 8px; border:1px solid black; border-radius:10px; font-family:Roboto,Helvetica,Arial,sans-serif;"><div><img style="float:left; margin-right:8px;" src="{0}"/><span style="line-height:48px; vertical-align:middle;"><b>{1}</b></span></div><br/><div style="clear:left;"></div>'.format(avatar, item['author']['name'])

    if state_json['user_post'].get('media'):
        for media in state_json['user_post']['media']:
            item['content_html'] += media

    item['content_html'] += '<p>{}</p><small>{}</p></div>'.format(item['summary'], item['_display_date'])
    return item


def get_track_content(track, args, save_debug=False):
    if save_debug:
        utils.write_file(track, './debug/debug.json')

    url = track['content']['metadata']['share_url']
    if url.startswith('https://bleacherreport.com/articles/'):
        return get_content(url, args, save_debug)

    if '/user_post/' in url:
        return get_user_post(url, args, save_debug)

    if track['content_type'] == 'poll' or track['content_type'] == 'external_article' or track['content_type'] == 'deeplink' or track['content_type'] == 'bet_track':
        logger.warning('skipping track content_type {} in {}'.format(track['content_type'], url))
        return None

    item = {}

    if track['content']['metadata'].get('stub_id'):
        item['id'] = track['content']['metadata']['stub_id']
    else:
        item['id'] = track['id']

    item['url'] = url

    if track['content']['metadata'].get('title'):
        item['title'] = track['content']['metadata']['title']
    elif track['content']['commentary'].get('title'):
        item['title'] = track['content']['commentary']['title']
    elif track['content']['metadata'].get('caption'):
        item['title'] = track['content']['metadata']['caption']
        if len(item['title']) > 50:
            m = re.search(r'^([\w\W\d\D\s]{50}[^\s]*)', item['title'], flags=re.S|re.U)
            item['title'] = m.group(1) + '...'

    dt = datetime.fromisoformat(track['created_at'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(track['updated_at'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if track['content']['metadata'].get('author_name'):
        item['author']['name'] = track['content']['metadata']['author_name']
    elif track.get('performed_by'):
        item['author']['name'] = track['performed_by']
    elif track['content']['metadata'].get('provider_name'):
        item['author']['name'] = track['content']['metadata']['provider_name']

    if track['content']['metadata'].get('tags'):
        item['tags'] = track['content']['metadata']['tags'].copy()
    elif track.get('tag'):
        item['tags'] = []
        item['tags'].append(track['tag']['display_name'])

    if track['content']['metadata'].get('thumbnail_url'):
        item['_image'] = resize_image(track['content']['metadata']['thumbnail_url'])

    if track['content']['metadata'].get('description'):
        item['summary'] = track['content']['metadata']['description']
    elif track['content'].get('commentary'):
        item['summary'] = track['content']['commentary']['description']

    if track['content_type'] == 'highlight':
        item['_video'] = track['content']['metadata']['mp4_url']
        item['content_html'] = utils.add_video(item['_video'], 'video/mp4', item['_image'], track['content']['title'])
        if item.get('summary'):
            item['content_html'] += '<p>{}</p>'.format(item['summary'])

    elif track['content_type'] == 'tweet':
        item['content_html'] = utils.add_embed(track['url'])
        if item.get('summary'):
            item['content_html'] += '<p>{}</p>'.format(item['summary'])

    return item

def get_content(url, args, save_debug=False):
    if '/post/' in url:
        post_json = utils.get_url_json('https://layserbeam-cached.bleacherreport.com/djay/content?url=' + quote_plus(url))
        if not post_json:
            return None
        return get_track_content(post_json['tracks'][0], args, save_debug)

    if '/user_post' in url:
        return get_user_post(url, args, save_debug)

    m = re.search(r'\/articles\/(\d+)', url)
    if not m:
        logger.warning('unhandled url ' + url)
        return None
    article_json = utils.get_url_json('https://layserbeam-cached.bleacherreport.com/articles/' + m.group(1))
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['breport_id']
    item['url'] = url
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['published_at']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['updated_at']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    item['author']['name'] = article_json['author']['name']

    if article_json.get('tag_list'):
        tags_json = utils.get_url_json('https://faust-cached.bleacherreport.com/tags/' + article_json['tag_list'])
        if tags_json:
            item['tags'] = []
            for tag in tags_json['tag']:
                item['tags'].append(tag['display_name'])

    item['_image'] = article_json['image']

    item['summary'] = article_json['description']

    item['content_html'] = ''
    for element in article_json['elements']:
        item['content_html'] += format_element(element)

    return item


def get_feed(args, save_debug=False):
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) > 0:
        feed_json = utils.get_url_json('https://layserbeam-cached.bleacherreport.com/djay/{}?limit=20'.format(paths[0]))
        if not feed_json:
            return None
        feed_tracks = feed_json['tracks']
    else:
        feed_json = utils.get_url_json('https://layserbeam-cached.bleacherreport.com/api/page/front-page')
        if not feed_json:
            return None
        feed_tracks = feed_json['sections']['trending']['tracks']

    if save_debug:
        utils.write_file(feed_json, './debug/feed.json')

    n = 0
    items = []
    for track in feed_tracks:
        if not track['content']['metadata'].get('share_url'):
            logger.warning('skipping ' + track['url'])
            continue
        if save_debug:
            logger.debug('getting content for ' + track['content']['metadata']['share_url'])
        if track['content_type'] == 'gamecast':
            game_json = utils.get_url_json('https://layserbeam-cached.bleacherreport.com' + re.sub('^\/game\/', '/gamecast/', track['permalink']))
            if game_json:
                for game_track in game_json['social']['tracks']:
                    item = get_track_content(game_track, args, save_debug)
                    if item:
                        if utils.filter_item(item, args) == True:
                            items.append(item)
                            n += 1
                            if 'max' in args:
                                if n == int(args['max']):
                                    break
        else:
            item = get_track_content(track, args, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break
    feed = utils.init_jsonfeed(args)
    uniq_items = {it['id']: it for it in items}.values()
    feed['items'] = sorted(uniq_items, key=lambda i: i['_timestamp'], reverse=True)
    #feed['items'] = sorted(items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
