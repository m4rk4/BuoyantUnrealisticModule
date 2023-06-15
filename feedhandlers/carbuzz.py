import re
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    if 'carbuzz.com/cars/' in url:
        page_html = utils.get_url_html(url)
        m = re.search(r'src="https://api\.carbuzz\.com/v\d\.0/tracking/post-view/([^"]+)"', page_html)
        if not m:
            logger.warning('unable to determine proper url for ' + url)
            return None
        api_url = 'https://api.carbuzz.com/v3.0/posts/' + m.group(1)
    else:
        split_url = urlsplit(url)
        api_url = 'https://api.carbuzz.com/v3.0/posts' + split_url.path
    api_url = api_url.replace('/features/', '/feature/')
    api_url = api_url.replace('/reviews/', '/review/')
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None

    content_json = api_json['content']
    if save_debug:
        utils.write_file(content_json, './debug/debug.json')

    item = {}
    item['id'] = content_json['postId']
    item['url'] = content_json['shareUrl']
    item['title'] = content_json['title']

    dt = datetime.fromisoformat(content_json['publishTimestamp'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
    dt = datetime.fromisoformat(content_json['lastUpdateTimestamp'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    item['author']['name'] = content_json['author']['displayName']

    item['tags'] = []
    for tag in content_json['tags']:
        item['tags'].append(tag['text'])

    content_html = ''
    if content_json.get('featuredImage'):
        item['_image'] = content_json['featuredImage']['baseUrl']
        img = utils.closest_dict(content_json['featuredImage']['formats'], 'width', 1000)
        img_src = content_json['featuredImage']['baseUrl'].replace('original', img['format'])
        if content_json['featuredImage'].get('creditName'):
            caption = content_json['featuredImage']['creditName']
        else:
            caption = ''
        content_html += utils.add_image(img_src, caption)

    if content_json.get('subTitle'):
        content_html += '<h3><em>{}</em></h3>'.format(content_json['subTitle'])

    for content_block in content_json['contentBlocks']:
        if content_block['blockType'] == 1 or content_block['blockType'] == 5 or content_block['blockType'] == 9:
            # 1, 9 = ads
            # 5 = related articles
            continue

        elif content_block['blockType'] == 0:
            # Formatted content
            if content_block.get('headline'):
                content_html += '<h3>{}</h3>'.format(content_block['headline'])
            content_html += content_block['content']

        elif content_block['blockType'] == 2:
            # Gallery
            for image in content_block['images']:
                if image['baseUrl'] == item['_image']:
                    continue
                img = utils.closest_dict(image['formats'], 'width', 1000)
                img_src = image['baseUrl'].replace('original', img['format'])
                if image.get('creditName'):
                    caption = image['creditName']
                else:
                    caption = ''
                content_html += utils.add_image(img_src, caption)

        elif content_block['blockType'] == 3:
            # Video (Youtube only?)
            if re.search(r'youtube\.com|youtu\.be', content_block['video']['videoUrl']):
                content_html += utils.add_youtube(content_block['video']['videoUrl'])
            else:
                logger.warning('unhandled video content in ' + api_url)
                content_html += '<p>Embedded video: <a href="{0}">{0}</a></p>'.format(
                    content_block['video']['videoUrl'])

        elif content_block['blockType'] == 14:
            # Twitter (only?)
            m = re.findall('https:\/\/twitter\.com\/[^\/]+\/statuse?s?\/\d+', content_block['html'])
            if m:
                content_html += utils.add_embed(m[-1])
            else:
                logger.warning('unhandled content block type {} in {}'.format(content_block['blockType'], api_url))

        elif content_block['blockType'] == 52 and content_block.get('blockKey') and content_block['blockKey'] == 'primis-block':
            # ads
            pass

        else:
            logger.warning('unhandled content block type {} in {}'.format(content_block['blockType'], api_url))

    if content_json.get('credits'):
        content_html += '<p>Source credits:<ul>'
        for credit in content_json['credits']:
            if credit.get('url'):
                # r = requests.head(credit['url'], allow_redirects=True)
                credit_url = utils.get_redirect_url(credit['url'])
                content_html += '<li><a href="{}">{}</a></li>'.format(credit_url, credit['name'])
            else:
                content_html += '<li>{}</li>'.format(credit['name'])
        content_html += '</ul><p>'

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', content_html)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
