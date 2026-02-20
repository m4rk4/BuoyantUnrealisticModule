import base64, curl_cffi, json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, image_utils, utils

import logging

logger = logging.getLogger(__name__)


# https://gist.github.com/sclark39/9daf13eea9c0b381667b61e3d2e7bc11?permalink_comment_id=5544964#gistcomment-5544964
def shortcode_to_id(shortcode: str) -> int:
    code = ('A' * (12-len(shortcode)))+shortcode
    return int.from_bytes(base64.b64decode(code.encode(), b'-_'), 'big')


def id_to_shortcode(pk: int) -> str:
    bytes_str = base64.b64encode(pk.to_bytes(9, 'big'), b'-_')
    return bytes_str.decode().replace('A', ' ').lstrip().replace(' ', 'A')


def get_user_profile(username, save_debug=False):
    r = curl_cffi.get('https://www.threads.com/@' + username, impersonate="chrome")
    if r.status_code == 200:
        if save_debug:
            utils.write_file(r.text, './debug/threads-user.html')
        soup = BeautifulSoup(r.text, 'lxml')
        el = soup.find('script', string=re.compile(r'follower_count'))
        if el:
            try:
                script_json = json.loads(el.string)
                user = script_json['require'][0][3][0]['__bbox']['require'][0][3][1]['__bbox']['result']['data']['user']
            except:
                user = None
        else:
            user = None
    if not user:
        logger.warning('unable to get user profile for ' + username)
    return user


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    post_id = paths[-1]

    r = curl_cffi.get(url, impersonate="chrome")
    if r.status_code == 200:
        if save_debug:
            utils.write_file(r.text, './debug/threads.html')
        soup = BeautifulSoup(r.text, 'lxml')
        el = soup.find('script', string=re.compile(r'XDTThread'))
        if el:
            try:
                script_json = json.loads(el.string)
                edges = script_json['require'][0][3][0]['__bbox']['require'][0][3][1]['__bbox']['result']['data']['data']['edges']
            except:
                logger.warning('unexpected json format in ' + url)
                return None
        else:
            logger.warning('unable to find XDTThread data in ' + url)
            return None

    if save_debug:
        utils.write_file(edges, './debug/threads.json')

    def get_thread_items(post_id, edges):
        item = {}
        for i, edge in enumerate(edges):
            for it in edge['node']['thread_items']:
                if i == 0:
                    if it['post']['code'] == post_id:
                        item |= get_item(it['post'])
                    else:
                        if '_parents' not in item:
                            item['_parents'] = []
                        item['_parents'].append(get_item(it['post']))
                else:
                    if it['post']['user']['username'] == item['author']['name']:
                        if 'children' not in item:
                            item['_children'] = []
                        item['children'].append(get_item(it['post']))
                    else:
                        return item
        return item
    item = get_thread_items(post_id, edges)
    item['content_html'] = utils.format_social_media_post(item, config.logo_threads, avatar_border_radius='50%', icon_verified=config.icon_verified)
    return item


def get_item(post_json):
    item = {}
    item['id'] = post_json['code']
    item['url'] = 'https://www.threads.com/@' + post_json['user']['username'] + '/post/' + post_json['code']
    item['title'] = 'Thread post by @' + post_json['user']['username']

    dt = datetime.fromtimestamp(post_json['taken_at']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {
        "url": 'https://threads.com/@' + post_json['user']['username'],
        "avatar": post_json['user']['profile_pic_url'],
        "_verified": post_json['user']['is_verified']
    }
    if post_json['user'].get('full_name'):
        item['author']['name'] = post_json['user']['full_name']
        item['author']['_username'] = '@' + post_json['user']['username']
    else:
        user = get_user_profile(post_json['user']['username'])
        if user:
            item['author']['name'] = user['full_name']
            item['author']['_username'] = '@' + post_json['user']['username']
        else:
            item['author']['name'] = post_json['user']['username']
    item['authors'] = []
    item['authors'].append(item['author'])

    if post_json.get('image_versions2') and post_json['image_versions2'].get('candidates'):
        image = utils.closest_dict(post_json['image_versions2']['candidates'], 'width', 640)
        item['image'] = image['url']

    if post_json.get('caption'):
        item['title'] += ': ' + post_json['caption']['text'].replace('\n', '')

    item['summary'] = ''
    if post_json.get('text_post_app_info') and post_json['text_post_app_info'].get('text_fragments') and post_json['text_post_app_info']['text_fragments'].get('fragments'):
        item['summary'] += '<p>'
        for it in post_json['text_post_app_info']['text_fragments']['fragments']:
            if it['fragment_type'] == 'plaintext':
                item['summary'] += it['plaintext'].replace('\n', '<br/>')
            elif it['fragment_type'] == 'link':
                item['summary'] += '<a href="' + it['link_fragment']['uri'] + '" target="_blank">' + it['link_fragment']['display_text'] + '</a>'
            elif it['fragment_type'] == 'mention':
                item['summary'] += '<a href="https://www.threads.com/@' + it['mention_fragment']['mentioned_user']['username'] + '" target="_blank">' + it['plaintext'] + '</a>'
            else:
                logger.warning('unhandled text fragment type ' + it['fragment_type'])
        item['summary'] += '</p>'

    item['_gallery'] = []
    if post_json.get('carousel_media'):
        carousel_media = post_json['carousel_media']
    elif post_json.get('text_post_app_info') and post_json['text_post_app_info'].get('linked_inline_media') and post_json['text_post_app_info']['linked_inline_media'].get('carousel_media'):
        carousel_media = post_json['text_post_app_info']['linked_inline_media']['carousel_media']
    else:
        carousel_media = None
    if carousel_media:
        for media in carousel_media:
            image = utils.closest_dict(media['image_versions2']['candidates'], 'width', 640)
            thumb = config.server + '/image?url=' + quote_plus(image['url'])
            image = utils.closest_dict(media['image_versions2']['candidates'], 'width', 1080)
            if media.get('video_versions'):
                item['_gallery'].append({
                    "src": media['video_versions'][0]['url'],
                    "thumb": thumb,
                    "width": media['original_width'],
                    "height": media['original_height'],
                    "video_type": "video/mp4",
                    "caption": ""
                })
            else:
                src = config.server + '/image?url=' + quote_plus(image['url'])
                item['_gallery'].append({
                    "src": src,
                    "thumb": thumb,
                    "width": media['original_width'],
                    "height": media['original_height'],
                    "caption": ""
                })
    elif post_json.get('video_versions'):
        image = utils.closest_dict(post_json['image_versions2']['candidates'], 'width', 640)
        thumb = config.server + '/image?url=' + quote_plus(image['url'])
        image = utils.closest_dict(post_json['image_versions2']['candidates'], 'width', 1080)
        item['_gallery'].append({
            "src": post_json['video_versions'][0]['url'],
            "thumb": thumb,
            "width": image['width'],
            "height": image['height'],
            "video_type": "video/mp4",
            "caption": ""
        })
    elif post_json.get('giphy_media_info'):
        thumb = re.sub(r'/[^/]+\.webp$', '/giphy_s.gif', post_json['giphy_media_info']['images']['fixed_height']['webp'])
        src = re.sub(r'/[^/]+\.webp$', '/giphy.mp4', post_json['giphy_media_info']['images']['fixed_height']['webp'])
        item['_gallery'].append({
            "src": src,
            "thumb": thumb,
            "width": post_json['giphy_media_info']['images']['fixed_height']['width'],
            "height": post_json['giphy_media_info']['images']['fixed_height']['height'],
            "video_type": "video/mp4",
            "caption": ""
        })
    elif post_json.get('image_versions2') and post_json['image_versions2'].get('candidates'):
        image = utils.closest_dict(post_json['image_versions2']['candidates'], 'width', 640)
        thumb = config.server + '/image?url=' + quote_plus(image['url'])
        image = utils.closest_dict(post_json['image_versions2']['candidates'], 'width', 1080)
        src = config.server + '/image?url=' + quote_plus(image['url'])
        item['_gallery'].append({
            "src": src,
            "thumb": thumb,
            "width": post_json['original_width'],
            "height": post_json['original_height'],
            "caption": ""
        })
    if len(item['_gallery']) == 0:
        del item['_gallery']

    if post_json.get('text_post_app_info') and post_json['text_post_app_info'].get('share_info') and post_json['text_post_app_info']['share_info'].get('quoted_post'):
        if post_json['text_post_app_info']['share_info']['quoted_post'].get('code'):
            item['_quote'] = get_item(post_json['text_post_app_info']['share_info']['quoted_post'])
        elif post_json['text_post_app_info']['share_info']['quoted_post'].get('id'):
            pk = int(post_json['text_post_app_info']['share_info']['quoted_post']['id'].split('_')[0])
            quote_url = 'https://www.threads.com/@' + post_json['text_post_app_info']['share_info']['quoted_post']['user']['username'] + '/post/' + id_to_shortcode(pk)
            quote_post = get_content(quote_url, {}, {}, False)
            if quote_post:
                item['_quote'] = quote_post
        elif post_json['text_post_app_info']['share_info'].get('quoted_post_caption'):
            item['summary'] += '<p style="margin-left:8px; font-size:smaller;>' + config.icon_left_quote + '&nbsp;' + post_json['text_post_app_info']['share_info']['quoted_post_caption'] + '&nbsp;' + config.icon_right_quote + '</p>'

    if post_json.get('text_post_app_info') and post_json['text_post_app_info'].get('link_preview_attachment'):
        link = post_json['text_post_app_info']['link_preview_attachment']['url']
        split_url = urlsplit(link)
        if split_url.netloc == 'l.threads.com':
            params = parse_qs(split_url.query)
            if params.get('u'):
                link = params['u'][0]
        item['_card'] = {
            "url": link,
            "title": post_json['text_post_app_info']['link_preview_attachment']['title'],
            "image": post_json['text_post_app_info']['link_preview_attachment']['image_url'],
            "_card_header": post_json['text_post_app_info']['link_preview_attachment']['display_url']
        }
        if post_json['text_post_app_info']['link_preview_attachment']['display_url'] == 'instagram.com':
            item['_card']['_card_style'] = 'small'

    return item


def format_post(post_json, post_style):
    user_url = 'https://www.threads.com/@' + post_json['user']['username']
    post_url = user_url + '/post/' + post_json['code']
    post_html = ''

    im_io = image_utils.read_image(post_json['user']['profile_pic_url'])
    if im_io:
        avatar = 'data:image/jpeg;base64,' + base64.b64encode(im_io.getvalue()).decode('utf-8')
    else:
        avatar = post_json['user']['profile_pic_url']

    if post_style == 'main':
        post_html += '<div style="display:grid; grid-template-areas:\'avatar name logo\' \'avatar username logo\' \'content content content\' \'date date date\'; grid-template-columns:3em auto 2.8em;">'
        post_html += '<div style="grid-area:logo; width:2.6em; height:3em; align-self:center;"><a href="' + post_url + '" target="_blank"><img src="data:image/svg+xml;base64,' + base64.b64encode(config.logo_threads.encode()).decode() + '" style="width:100%;"></a></div>'
    elif post_style == 'ancestor':
        post_html += '<div style="display:grid; grid-template-areas:\'avatar avatar name\' \'avatar avatar username\' \'col1 col2 content\' \'col1 col2 date\' \'post1 post2 empty\'; grid-template-columns:1.6em 1.4em auto; font-size:smaller;">'
        post_html += '<div style="grid-area:col1; border-right:3px solid light-dark(#ccc,#333);"></div>'
        post_html += '<div style="grid-area:post1; border-right:3px solid light-dark(#ccc,#333); height:2em;"></div>'
    elif post_style == 'descendent':
        post_html += '<div style="display:grid; grid-template-areas:\'pre1 pre2 empty\' \'avatar avatar name\' \'avatar avatar username\' \'col1 col2 content\' \'col1 col2 date\'; grid-template-columns:1.6em 1.4em auto; font-size:smaller;">'
        post_html += '<div style="grid-area:pre1; border-right:3px solid light-dark(#ccc,#333); height:2em;"></div>'
        post_html += '<div style="grid-area:col1; border-right:3px solid light-dark(#ccc,#333);"></div>'
    elif post_style == 'quote':
        post_html += '<div style="display:grid; grid-template-areas:\'avatar username\' \'content content\' \'date date\'; grid-template-columns:2.5em auto; font-size:smaller;">'

        post_html += '<div style="grid-area:avatar; width:2.5em; height:2.5em;"><a href="' + user_url + '" target="_blank"><img src="' + avatar + '" style="width:100%; border-radius:50%;"></a></div>'

        post_html += '<div style="grid-area:username; align-self:center; padding-left:0.5em;"><a href="' + user_url + '" target="_blank" style="text-decoration:none;"><b>@' + post_json['user']['username'] + '</b></a>'
        if post_json['user']['is_verified']:
            post_html += ' <img src="data:image/svg+xml;base64,' + base64.b64encode(config.icon_verified.encode()).decode() + '" style="width:1em; height:1em;">'
        post_html += '</div>'

    if post_style != 'quote':
        post_html += '<div style="grid-area:avatar; width:3em; height:3em;"><a href="' + user_url + '" target="_blank"><img src="' + avatar + '" style="width:100%; border-radius:50%;"></a></div>'

        post_html += '<div style="grid-area:name; align-self:end; padding-left:0.5em;"><a href="' + user_url + '" target="_blank" style="text-decoration:none;"><b>' + post_json['user']['full_name'] + '</b></a>'
        if post_json['user']['is_verified']:
            post_html += ' <img src="data:image/svg+xml;base64,' + base64.b64encode(config.icon_verified.encode()).decode() + '" style="width:1em; height:1em;">'
        post_html += '</div>'

        post_html += '<div style="grid-area:username; align-self:start; padding-left:0.5em; font-size:smaller;"><a href="' + user_url + '" target="_blank" style="text-decoration:none;">@' + post_json['user']['username'] + '</a></div>'

    post_html += '<div style="grid-area:content;">'

    if post_json.get('text_post_app_info') and post_json['text_post_app_info'].get('text_fragments') and post_json['text_post_app_info']['text_fragments'].get('fragments'):
        post_html += '<p>'
        for it in post_json['text_post_app_info']['text_fragments']['fragments']:
            if it['fragment_type'] == 'plaintext':
                post_html += it['plaintext'].replace('\n', '<br/>')
            elif it['fragment_type'] == 'link':
                post_html += '<a href="' + it['link_fragment']['uri'] + '" target="_blank">' + it['link_fragment']['display_text'] + '</a>'
            else:
                logger.warning('unhandled text fragment type ' + it['fragment_type'])
        post_html += '</p>'

    if post_json.get('carousel_media'):
        carousel_aspect_ratio = '{}/{}'.format(post_json['original_width'], post_json['original_height'])
        carousel_media = post_json['carousel_media']
    elif post_json.get('text_post_app_info') and post_json['text_post_app_info'].get('linked_inline_media') and post_json['text_post_app_info']['linked_inline_media'].get('carousel_media'):
        carousel_media = post_json['text_post_app_info']['linked_inline_media']['carousel_media']
        carousel_aspect_ratio = '{}/{}'.format(post_json['text_post_app_info']['linked_inline_media']['original_width'], post_json['text_post_app_info']['linked_inline_media']['original_height'])
    else:
        carousel_media = None
    if carousel_media:
        gallery_images = []
        for it in carousel_media:
            media = {}
            image = utils.closest_dict(it['image_versions2']['candidates'], 'width', 640)
            media['thumb'] = config.server + '/image?url=' + quote_plus(image['url'])
            if it.get('video_versions'):
                media['src'] = it['video_versions'][0]['url']
                media['video_type'] = 'video/mp4'
            else:
                image = utils.closest_dict(it['image_versions2']['candidates'], 'width', 1080)
                media['src'] = config.server + '/image?url=' + quote_plus(image['url'])
            gallery_images.append(media)
        post_html += utils.add_carousel(gallery_images, carousel_aspect_ratio, border_radius='10px')

    elif post_json.get('video_versions'):
        image = utils.closest_dict(post_json['image_versions2']['candidates'], 'width', 640)
        thumb = config.server + '/image?url=' + quote_plus(image['url'])
        video_src = config.server + '/videojs?src=' + quote_plus(post_json['video_versions'][0]['url']) + '&type=video%2Fmp4&poster=' + quote_plus(thumb)
        overlay = config.video_button_overlay
        post_html += '<div style="position:relative; z-index:1; margin:1em auto;"><a href="' + video_src + '" target="_blank"><img src="' + thumb + '" loading="lazy" style="display:block; margin:0 auto; object-fit:contain; width:100%; border-radius:10px;"><div style="position:absolute; z-index:2; top:0; left:0; bottom:0; right:0; background:url(\'' + overlay['src'] + '\') no-repeat center center; background-size:' + overlay['size'] + '; filter:' + overlay['filter'] + ';"></div></a></div>'

    elif post_json.get('giphy_media_info'):
        thumb = re.sub(r'/[^/]+\.webp$', '/giphy_s.gif', post_json['giphy_media_info']['images']['fixed_height']['webp'])
        src = re.sub(r'/[^/]+\.webp$', '/giphy.mp4', post_json['giphy_media_info']['images']['fixed_height']['webp'])
        video_src = config.server + '/videojs?src=' + quote_plus(src) + '&type=video%2Fmp4&poster=' + quote_plus(thumb)
        overlay = config.video_button_overlay
        post_html += '<div style="position:relative; z-index:1; margin:1em auto;"><a href="' + video_src + '" target="_blank"><img src="' + thumb + '" loading="lazy" style="display:block; margin:0 auto; object-fit:contain; width:100%; border-radius:10px;"><div style="position:absolute; z-index:2; top:0; left:0; bottom:0; right:0; background:url(\'' + overlay['src'] + '\') no-repeat center center; background-size:' + overlay['size'] + '; filter:' + overlay['filter'] + ';"></div></a></div>'

    elif post_json.get('image_versions2') and post_json['image_versions2'].get('candidates'):
        image = utils.closest_dict(post_json['image_versions2']['candidates'], 'width', 1080)
        src = config.server + '/image?url=' + quote_plus(image['url'])
        image = utils.closest_dict(post_json['image_versions2']['candidates'], 'width', 640)
        thumb = config.server + '/image?url=' + quote_plus(image['url'])
        post_html += '<a href="' + src + '" target="_blank"><div style="display:flex; align-items:center; justify-content:center; margin:1em auto;"><img src="' + thumb + '" style="max-width:100%; max-height:540px; border-radius:10px;"></div></a>'

    if post_json.get('text_post_app_info') and post_json['text_post_app_info'].get('share_info') and post_json['text_post_app_info']['share_info'].get('quoted_post'):
        if post_json['text_post_app_info']['share_info']['quoted_post'].get('code'):
            post_html += '<div style="margin:1em auto; padding:8px; border:1px solid light-dark(#333,#ccc); border-radius:10px;">' + format_post(post_json['text_post_app_info']['share_info']['quoted_post'], 'quote') + '</div>'
        elif post_json['text_post_app_info']['share_info']['quoted_post'].get('id'):
            pk = int(post_json['text_post_app_info']['share_info']['quoted_post']['id'].split('_')[0])
            quote_url = 'https://www.threads.com/@' + post_json['text_post_app_info']['share_info']['quoted_post']['user']['username'] + '/post/' + id_to_shortcode(pk)
            quote_post = get_content(quote_url, {"post_style": "quote"}, {}, False)
            if quote_post:
                post_html += '<div style="margin:1em auto; padding:8px; border:1px solid light-dark(#333,#ccc); border-radius:10px;">' + quote_post['content_html'] + '</div>'
        elif post_json['text_post_app_info']['share_info'].get('quoted_post_caption'):
            post_html += '<p style="margin-left:8px; font-size:smaller;>' + config.icon_left_quote + '&nbsp;' + post_json['text_post_app_info']['share_info']['quoted_post_caption'] + '&nbsp;' + config.icon_right_quote + '</p>'

    elif post_json.get('text_post_app_info') and post_json['text_post_app_info'].get('link_preview_attachment'):
        link = post_json['text_post_app_info']['link_preview_attachment']['url']
        split_url = urlsplit(link)
        if split_url.netloc == 'l.threads.com':
            params = parse_qs(split_url.query)
            if params.get('u'):
                link = params['u'][0]
        post_html += utils.add_large_card(post_json['text_post_app_info']['link_preview_attachment']['image_url'], None, link, post_json['text_post_app_info']['link_preview_attachment']['display_url'], post_json['text_post_app_info']['link_preview_attachment']['title'])

    if post_json.get('text_post_app_info') and post_json['text_post_app_info'].get('tag_header'):
        post_html += '<p><img src="data:image/svg+xml;base64,' + base64.b64encode(config.icon_open_url.encode()).decode() + '" style="width:1em; height:1em;">&nbsp;<a href="https://www.threads.com/search?q=' + quote_plus(post_json['text_post_app_info']['tag_header']['tag_cluster_name']) + '&serp_type=tags&tag_id=' + post_json['text_post_app_info']['tag_header']['id'] + '" target="_blank">' + post_json['text_post_app_info']['tag_header']['display_name'] + '</a></p>'

    post_html += '</div>'

    dt = datetime.fromtimestamp(post_json['taken_at']).replace(tzinfo=timezone.utc)
    post_html += '<div style="grid-area:date; margin-top:0.5em; font-size:smaller;"><a href="' + post_url + '" target="_blank" style="text-decoration:none;">' + utils.format_display_date(dt) + '</a></div>'

    post_html += '</div>'
    return post_html