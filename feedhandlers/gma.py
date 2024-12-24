import re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)



def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    id = paths[-3]

    item = {}
    content_json = None
    if 'story' in paths:
        if 'entertainment' in paths:
            api_url = 'https://data.igma.tv/entertainment/{}/entertainment/articles/{}.gz'.format(id[:-4:-1], id)
        else:
            api_url = 'https://data2.gmanetwork.com/{}/gno/story/{}.gz'.format(id[:-4:-1], id)
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        if api_json.get('story'):
            content_json = api_json['story']
        else:
            content_json = api_json
    elif 'video' in paths:
        api_url = 'https://data.igma.tv/entertainment/{}/entertainment/videos/{}.gz'.format(id[:-4:-1], id)
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/debug.json')
        content_json = api_json
        item['authors'] = [{"name": "GMA Entertainment"}]
    elif 'photo' in paths:
        api_url = 'https://data.igma.tv/entertainment/{}/entertainment/photos/{}.gz'.format(id[:-4:-1], id)
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/debug.json')
        content_json = api_json['gallery_info']
        item['authors'] = [{"name": "GMA Entertainment"}]
    else:
        logger.warning('unhandled url ' + url)
        return None

    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    item = {}
    item['id'] = content_json['id']

    if 'entertainment' in paths:
        item['url'] = '{}://{}/entertainment/{}'.format(split_url.scheme, split_url.netloc, content_json['override_url'])
    elif content_json.get('section'):
        item['url'] = '{}://{}/{}/{}'.format(split_url.scheme, split_url.netloc, content_json['section']['sec_stub'], content_json['article_url'])

    item['title'] = content_json['title']

    if content_json.get('timestamp'):
        dt = datetime.fromisoformat(content_json['timestamp'] + '+08:00').astimezone(timezone.utc)
    elif content_json.get('publish_date'):
        # entertainment
        dt = dateutil.parser.parse(content_json['publish_date'] + '+08:00').astimezone(timezone.utc)
    else:
        dt = None    
    if dt:
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    if content_json.get('updated_as_of') and not content_json['updated_as_of'].startswith('0000'):
        dt = datetime.fromisoformat(content_json['updated_as_of'] + '+08:00').astimezone(timezone.utc)
    elif content_json.get('updated_when') and not content_json['updated_when'].startswith('0000'):
        dt = datetime.fromisoformat(content_json['updated_when'] + '+08:00').astimezone(timezone.utc)
    elif content_json.get('update_timestamp') and not content_json['update_timestamp'].startswith('0000'):
        # entertainment
        dt = datetime.fromisoformat(content_json['update_timestamp'] + '+08:00').astimezone(timezone.utc)
    else:
        dt = None
    if dt:
        item['date_modified'] = dt.isoformat()

    if content_json.get('special_author'):
        item['authors'] = [{"name": x} for x in content_json['special_author'].split(',')]
    elif content_json.get('contributors'):
        item['authors'] = [{"name": x['full_name']} for x in content_json['contributors']]
    elif content_json.get('ga_author'):
        item['authors'] = [{"name": content_json['ga_author']}]
    elif content_json.get('article_source'):
        item['authors'] = [{"name": content_json['article_source']['source_name']}]
    elif content_json.get('content_source'):
        item['authors'] = [{"name": content_json['content_source']}]
    if 'authors' in item:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    if api_json.get('all_tags'):
        item['tags'] = api_json['all_tags'].copy()
    elif content_json.get('tags'):
        item['tags'] = content_json['tags'].split(' ')
    elif content_json.get('keywords'):
        if 'entertainment' in paths:
            item['tags'] = content_json['keywords'].split(',')
        else:
            item['tags'] = content_json['keywords'].split(' ')

    if content_json.get('teaser'):
        item['summary'] = content_json['teaser']
    elif content_json.get('description'):
        if 'photo' in paths:
            m = re.findall(r'<p>.*?</p>', content_json['description'])
            item['summary'] = ''.join(m[0:2])
        else:
            item['summary'] = content_json['description']

    if content_json.get('image_url'):
        item['image'] = content_json['image_url']
    elif content_json.get('image') and 'entertainment' in paths:
        # TODO: is size always 900x675?
        if 'video' in paths:
            item['image'] = 'https://aphrodite.gmanetwork.com/entertainment/videos/images/900_675_' + content_json['image']
        elif 'photo' in paths:
            item['image'] = 'https://aphrodite.gmanetwork.com/entertainment/gallery/900_675_' + content_json['image']
        else:
            item['image'] = 'https://aphrodite.gmanetwork.com/entertainment/articles/900_675_' + content_json['image']

    item['content_html'] = ''

    if 'video' in paths:
        if content_json.get('video_file'):
            item['content_html'] = utils.add_embed('https://www.youtube.com/watch?v=' + content_json['video_file'])
        else:
            logger.warning('unhandled video content in ' + item['url'])
        if content_json.get('description') and 'embed' not in args:
            item['content_html'] += '<p>' + content_json['description'] + '</p>'
        return item

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if content_json.get('cover_photo_video_content'):
        if content_json['cover_photo_video_id'] == '2':
            item['content_html'] += utils.add_image(content_json['cover_photo_video_content'], content_json.get('cover_photo_video_caption'))
        elif content_json['cover_photo_video_id'] == '5':
            m = re.search(r'src="([^"]+)"', content_json['cover_photo_video_content'])
            if m:
                item['content_html'] += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled cover_photo_video_content in ' + item['url'])
        else:
            logger.warning('unhandled cover_photo_video_content in ' + item['url'])
    elif api_json.get('cover_info'):
        if api_json['cover_info'].get('youtube_id'):
            item['content_html'] = utils.add_embed('https://www.youtube.com/watch?v=' + api_json['cover_info']['youtube_id'])
        elif api_json['cover_info'].get('image'):
            # TODO: caption?
            if 'photo' in paths:
                item['content_html'] += utils.add_image('https://aphrodite.gmanetwork.com/entertainment/gallery/900_675_' + api_json['cover_info']['image'])
            else:
                item['content_html'] += utils.add_image('https://aphrodite.gmanetwork.com/entertainment/articles/900_675_' + api_json['cover_info']['image'])
        else:
            logger.warning('unhandled cover_info content in ' + item['url'])

    if content_json.get('content_1'):
        soup = BeautifulSoup(content_json['content_1'], 'html.parser')
    elif content_json.get('body'):
        soup = BeautifulSoup(content_json['body'], 'html.parser')
    elif 'photo' in paths and content_json.get('description'):
        soup = BeautifulSoup(content_json['description'], 'html.parser')
    else:
        logger.warning('unknown content in ' + item['url'])
        soup = None

    if soup:
        for el in soup.find_all('iframe'):
            new_html = utils.add_embed(el['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

        item['content_html'] += str(soup)

    if api_json.get('allphotos'):
        item['_gallery'] = []
        item['content_html'] += '<h2><a href="{}/gallery?url={}">View slideshow</a></h2>'.format(config.server, quote_plus(item['url']))
        item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
        for photo in api_json['allphotos']:
            img_src = 'https://aphrodite.gmanetwork.com/entertainment/photos/photo/' + photo['photo_file']
            thumb = 'https://aphrodite.gmanetwork.com/entertainment/photos/large/' + photo['photo_file']
            if photo.get('author'):
                caption = photo['author']
            else:
                caption = ''
            desc = ''
            if photo.get('title'):
                desc += '<h3>' + photo['title'] + '</h3>'
            if photo.get('description'):
                desc += photo['description']
            item['_gallery'].append({"src": img_src, "caption": caption, "thumb": thumb, "desc": desc})
            item['content_html'] += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img_src, desc=desc) + '</div>'
        item['content_html'] += '</div>'
    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://www.gmanetwork.com/news/rss/
    return rss.get_feed(url, args, site_json, save_debug, get_content)
