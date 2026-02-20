import json, math, pytz, random, re, string
import base64, hmac, hashlib, os, time
import curl_cffi, requests, requests_toolbelt, rnet
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlencode, urlsplit

import config, image_utils, utils

import logging

logger = logging.getLogger(__name__)


def format_content(item):
    n = len(item['authors'])
    w = 32 + 16 * (n - 1) + 16
    item['content_html'] = '<div style="min-width:320px; max-width:540px; margin:1em auto; border:1px solid light-dark(#333,#ccc);"><div style="display:grid; grid-template-areas:\'avatar username logo\'  \'media media media\' \'content content content\' \'date date date\'; grid-template-columns:{}px auto 48px; font-size:smaller;">'.format(w)
    if n == 1:
        im_io = image_utils.read_image(item['authors'][0]['avatar'])
        if im_io:
            src = 'data:image/jpeg;base64,' + base64.b64encode(im_io.getvalue()).decode('utf-8')
        else:
            src = it['avatar']
        item['content_html'] += '<div style="grid-area:avatar; width:32px; height:32px; padding:8px;"><a href="' + item['authors'][0]['url'] + '" target="_blank"><img src="' + src + '" style="width:100%; border-radius:100%;"></a></div>'
    else:
        item['content_html'] += '<div style="grid-area:avatar; width:{}px; height:32px; padding:8px; position:relative;">'.format(w)
        for i, it in enumerate(item['authors']):
            im_io = image_utils.read_image(it['avatar'])
            if im_io:
                src = 'data:image/jpeg;base64,' + base64.b64encode(im_io.getvalue()).decode('utf-8')
            else:
                src = it['avatar']
            if i == 0:
                item['content_html'] += '<a href="' + it['url'] + '" target="_blank"><img src="' + src + '" style="display:block; width:32px; height:32px; border-radius:100%;"></a>'
            else:
                item['content_html'] += '<a href="' + it['url'] + '" target="_blank"><img src="' + src + '" style="position:absolute; top:8px; left:' + str(16*i) + 'px; z-index:-' + str(i) + '; width:32px; height:32px; border-radius:100%;"></a>'
        item['content_html'] += '</div>'

    item['content_html'] += '<div style="grid-area:username; align-self:center; font-weight:bold;">' + re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(['<a href="' + x['url'] + ' target="_blank">' + x['name'] + '</a>' for x in item['authors']])) + '</div>'

    item['content_html'] += '<div style="grid-area:logo; width:32px; height:32px; padding:8px;"><a href="' + item['url'] + '" target="_blank"><img src="data:image/svg+xml;base64,' + base64.b64encode(config.logo_instagram.encode()).decode() + '" style="width:100%;"></a></div>'

    if '_media' in item:
        item['content_html'] += '<div style="grid-area:media;">'
        if len(item['_media']) > 1:
            item['content_html'] += utils.add_carousel(item['_media'], aspect_ratio=item['_media_aspect_ratio'], margin='0')
        else:
            if '_media_aspect_ratio' in item:
                x = item['_media_aspect_ratio'].split('/')
                if int(x[0]) > int(x[1]):
                    # default
                    img_style='width:100%; max-height:800px; object-fit:contain;'
                else:
                    img_style='width:100%; aspect-ratio:2/3; object-fit:cover;'
            if 'video_type' in item['_media'][0]:
                item['content_html'] += utils.add_video(item['_media'][0]['src'], item['_media'][0]['video_type'], item['_media'][0]['thumb'], item['_media'][0]['caption'], img_style=img_style, fig_style='margin:0; padding:0;', use_videojs=True)
            else:
                item['content_html'] += utils.add_image(item['_media'][0]['thumb'], link=item['_media'][0]['src'], img_style=img_style, fig_style='margin:0; padding:0;')

    item['content_html'] += '</div><div style="grid-area:content; margin:0 8px;"><p><a href="' + item['authors'][0]['url'] + ' target="_blank" style="text-decoration:none;"><strong>' + item['authors'][0]['name'] + '</strong></a>'
    if item['authors'][0]['verified']:
        item['content_html'] += ' <img src="data:image/svg+xml;base64,' + base64.b64encode(config.icon_verified.encode()).decode() + '" style="width:1em; height:1em;">'
    item['content_html'] += '</p><p>' + item['summary'] + '</p></div>'

    item['content_html'] += '<div style="grid-area:date; margin:8px; font-size:small;"><a href="' + item['url'] + '" target="_blank" style="text-decoration:none;">' + item['_display_date'] + '</a></div>'

    item['content_html'] += '</div></div>'


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    ig_id = paths[-1]
    ig_url = 'https://www.instagram.com/' + paths[-2] + '/' + ig_id + '/'
    embed_url = ig_url + 'embed/captioned/?cr=1&v=14&wp=540'
    ig_data = None
    ig_profile = None
    username = ''
    user_id = ''
    item = {}

    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "sec-ch-prefers-color-scheme": "light",
        "sec-ch-ua": "\"Not(A:Brand\";v=\"8\", \"Chromium\";v=\"144\", \"Microsoft Edge\";v=\"144\"",
        "sec-ch-ua-full-version-list": "\"Not(A:Brand\";v=\"8.0.0.0\", \"Chromium\";v=\"144.0.7559.110\", \"Microsoft Edge\";v=\"144.0.3719.104\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-model": "\"\"",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-ch-ua-platform-version": "\"15.0.0\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-asbd-id": "359341",
        "x-csrftoken": "",
        "x-ig-app-id": "",
        "x-ig-www-claim": "0",
        "x-requested-with": "XMLHttpRequest",
        "x-web-session-id": ""
    }
    # x-asbd-id seems to be a fixed value. Not sure when it changes.
    # headers['x-asbd-id'] = "359341"
    headers['x-web-session-id'] = utils.base36encode(math.floor(random.random() * 2176782336)).zfill(6) + ':' + utils.base36encode(math.floor(random.random() * 2176782336)).zfill(6) + ':' + utils.base36encode(math.floor(random.random() * 2176782336)).zfill(6)

    # Try to find json in embed page
    r = curl_cffi.get(embed_url, impersonate="chrome")
    if r.status_code == 200:
        if save_debug:
            utils.write_file(r.text, './debug/ig_embed.html')
        soup = BeautifulSoup(r.text, 'lxml')
        el = soup.find('script', string=re.compile(r'PolarisEmbedSimple'))
        if el:
            i = el.string.find('{"define":')
            j = el.string.rfind(');requireLazy')
            script_json = json.loads(el.string[i:j])
            if save_debug:
                utils.write_file(script_json, './debug/ig_script.json')
            for it in script_json['require']:
                if 'PolarisEmbedSimple' in it and it[3][0].get('contextJSON'):
                    ig_data = json.loads(it[3][0]['contextJSON'])
                    break
        m = re.search(r'"csrf_token":"([^"]+)', r.text)
        if m:
            headers['x-csrftoken'] = m.group(1)
        m = re.search(r'"X-IG-App-ID":"([^"]+)', r.text)
        if m:
            headers['x-ig-app-id'] = m.group(1)
        m = re.search(r'"Instagram post shared by &#064;([^"]+)"', r.text)
        if m:
            username = m.group(1)
        m = re.search(r'data-owner-id="(\d+)"', r.text)
        if m:
            user_id = m.group(1)

    if not ig_data:
        logger.debug('IG data not found in embed page. Checking ' + ig_url)
        # client = rnet.blocking.Client()
        # try:
        #     r = client.get(ig_url, emulation=rnet.Emulation.Safari26, proxy=rnet.Proxy.all(config.http_proxy))
        #     r.raise_for_status()
        # except Exception as e:
        #     logger.warning('error getting {}, status code {}'.format(ig_url, str(r.status)))
        #     return None
        # if save_debug:
        #     utils.write_file(r.text(), './debug/ig_url.html')
        r = curl_cffi.get(ig_url, impersonate="chrome")
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            el = soup.find('script', string=re.compile(r'xdt_api__v1__media__shortcode__web_info|xdt_api__v1__clips__clips_on_logged_out_connection_v2'))
            if el:
                script_json = json.loads(el.string)
                if save_debug:
                    utils.write_file(script_json, './debug/ig_script.json')
                try:
                    if 'xdt_api__v1__media__shortcode__web_info' in script_json['require'][0][3][0]['__bbox']['require'][0][3][1]['__bbox']['result']['data']:
                        ig_data = script_json['require'][0][3][0]['__bbox']['require'][0][3][1]['__bbox']['result']['data']['xdt_api__v1__media__shortcode__web_info']['items'][0]
                    else:
                        ig_data = script_json['require'][0][3][0]['__bbox']['require'][0][3][1]['__bbox']['result']['data']['xdt_api__v1__clips__clips_on_logged_out_connection_v2']['edges'][0]['node']['media']
                except:
                    logger.warning('did not find xdt_api__v1__ info in ' + ig_url)
            m = re.search(r'"csrf_token":"([^"]+)', r.text)
            if m:
                headers['x-csrftoken'] = m.group(1)
            m = re.search(r'"X-IG-App-ID":"([^"]+)', r.text)
            if m:
                headers['x-ig-app-id'] = m.group(1)
            if not username:
                m = re.search(r'"pk":"(\d+)","username":"([^"]+)","id":"(\d+)"', r.text)
                if m:
                    username = m.group(2)
                    user_id = m.group(3)

    r = curl_cffi.get('https://www.instagram.com/api/v1/users/web_profile_info/?username=' + username, headers=headers, impersonate='chrome')
    if r.status_code == 200:
        ig_profile = r.json()['data']['user']
        if save_debug:
            utils.write_file(ig_profile, './debug/ig_profile.json')
        if not ig_data:
            logger.debug('IG data not found in web page. Checking user profile...')
            ig_data = next((it for it in ig_profile['edge_owner_to_timeline_media']['edges'] if it['node']['shortcode'] == ig_id), None)
            if not ig_data:
                ig_data = next((it for it in ig_profile['edge_felix_video_timeline']['edges'] if it['node']['shortcode'] == ig_id), None)

    if not ig_data:
        logger.warning('unable to get IG json data for ' + url)
        return None

    if save_debug:
        utils.write_file(ig_data, './debug/ig.json')

    if '__typename' in ig_data and ig_data['__typename'] != 'XDTMediaDict':
        item['id'] = ig_data['shortcode']
        item['url'] = ig_url
        item['title'] = 'An Instagram post by @' + ig_data['owner']['username']

        dt = datetime.fromtimestamp(ig_data['taken_at_timestamp']).replace(tzinfo=timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

        item['authors'] = []
        item['author'] = {
            "name": ig_data['owner']['username'],
            "url": 'https://www.instagram.com/' + ig_data['owner']['username'],
            "avatar": ig_data['owner']['profile_pic_url'],
            "verified": ig_data['owner']['is_verified']
        }
        if ig_data['owner'].get('profile_pic_url'):
            item['author']['avatar'] = ig_data['owner']['profile_pic_url']
        elif ig_profile:
            item['author']['avatar'] = ig_profile['profile_pic_url']
        if ig_data['owner'].get('is_verified'):
            item['author']['verified'] = ig_data['owner']['is_verified']
        elif ig_profile:
            item['author']['verified'] = ig_profile['is_verified']
        item['authors'] = []
        item['authors'].append(item['author'])

        if ig_data.get('coauthor_producers'):
            for it in ig_data['coauthor_producers']:
                item['authors'].append({
                    "name": it['username'],
                    "url": 'https://www.instagram.com/' + it['username'],
                    "avatar": it['profile_pic_url']
                })
            item['author'] = {
                "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
            }

        if ig_data.get('thumbnail_src'):
            item['image'] = ig_data['thumbnail_src']

        if ig_data['edge_media_to_caption'].get('edges'):
            item['summary'] = ig_data['edge_media_to_caption']['edges'][0]['node']['text']

        if ig_data['__typename'] == 'GraphImage':
            item['_media_aspect_ratio'] = '{}/{}'.format(ig_data['dimensions']['width'], ig_data['dimensions']['height'])
            item['_media'] = []
            item['_media'].append({"src": ig_data['display_url'], "caption": "", "thumb": ig_data['thumbnail_src']})
        elif ig_data['__typename'] == 'GraphVideo':
            item['_media_aspect_ratio'] = '{}/{}'.format(ig_data['dimensions']['width'], ig_data['dimensions']['height'])
            item['_media'] = []
            item['_media'].append({"src": ig_data['video_url'], "caption": "", "thumb": ig_data['thumbnail_src'], "video_type": "video/mp4"})
        elif ig_data['__typename'] == 'GraphSidecar':
            item['_media_aspect_ratio'] = '{}/{}'.format(ig_data['dimensions']['width'], ig_data['dimensions']['height'])
            item['_media'] = []
            for it in ig_data['edge_sidecar_to_children']['edges']:
                if it['node']['__typename'] == 'GraphImage':
                    item['_media'].append({"src": it['node']['display_url'], "caption": "", "thumb": it['node']['display_url']})
                elif it['node']['__typename'] == 'GraphVideo':
                    item['_media'].append({"src": it['node']['video_url'], "caption": "", "thumb": it['node']['display_url'], "video_type": "video/mp4"})
        else:
            logger.warning('unhandled ig data type ' + ig_data['__typename'])
    elif 'context' in ig_data:
        ig_context = ig_data['context']
        item['id'] = ig_context['shortcode']
        item['url'] = ig_context['media_canonical']
        item['title'] = ig_context['alt_text']

        dt = datetime.fromtimestamp(ig_context['media']['taken_at_timestamp']).replace(tzinfo=timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

        item['author'] = {
            "name": ig_context['media']['owner']['username'],
            "url": 'https://www.instagram.com/' + ig_context['media']['owner']['username'],
            "avatar": ig_context['media']['owner']['profile_pic_url'],
            "verified": ig_context['media']['owner']['is_verified']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

        if ig_context['media'].get('coauthor_producers'):
            for it in ig_context['media']['coauthor_producers']:
                item['authors'].append({
                    "name": it['username'],
                    "url": 'https://www.instagram.com/' + it['username'],
                    "avatar": it['profile_pic_url']
                })
            item['author'] = {
                "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
            }

        item['summary'] = re.sub(r'^(<br/>)+', '', ig_context['caption_title_linkified'])
        item['summary'] = re.sub(r'href="/', 'href="https://www.instagram.com/', item['summary'])
        item['summary'] = re.sub(r'\s*(class|data-ios-link|data-log-event)="[^"]+"', '', item['summary'])

        item['_media'] = []
        if ig_context['type'] == 'GraphVideo':
            item['_media_aspect_ratio'] = '{}/{}'.format(ig_context['media']['dimensions']['width'], ig_context['media']['dimensions']['height'])
            image = utils.closest_dict(ig_context['media']['display_resources'], 'config_width', 640)
            thumb = config.server + '/image?url=' + quote_plus(image['src'])
            if ig_context['media'].get('clips_music_attribution_info') and ig_context['media']['clips_music_attribution_info'].get('artist_name'):
                caption = '🎵 ' + ig_context['media']['clips_music_attribution_info']['artist_name'] + ' &bull; ' + ig_context['media']['clips_music_attribution_info']['song_name']
            else:
                caption = ''
            item['_media'].append({"src": ig_context['media']['video_url'], "caption": caption, "thumb": thumb, "video_type": "video/mp4"})
        elif ig_context['media']['edge_sidecar_to_children'].get('edges'):
            edge = ig_context['media']['edge_sidecar_to_children']['edges'][0]
            item['_media_aspect_ratio'] = '{}/{}'.format(edge['node']['dimensions']['width'], edge['node']['dimensions']['height'])
            for edge in ig_context['media']['edge_sidecar_to_children']['edges']:
                if edge['node']['__typename'] == 'GraphImage':
                    image = utils.closest_dict(edge['node']['display_resources'], 'config_width', 1080)
                    # src = image['src']
                    src = config.server + '/image?url=' + quote_plus(image['src'])
                    image = utils.closest_dict(edge['node']['display_resources'], 'config_width', 640)
                    # thumb = image['src']
                    thumb = config.server + '/image?url=' + quote_plus(image['src'])
                    item['_media'].append({"src": src, "caption": "", "thumb": thumb})
                else:
                    logger.warning('unhandled media edge node type ' + edge['node']['__typename'])
    else:
        item['id'] = ig_data['code']
        item['url'] = ig_url
        el = soup.find('meta', attrs={"property": "og:title"})
        if el:
            item['title'] = el['content']

        dt = datetime.fromtimestamp(ig_data['taken_at']).replace(tzinfo=timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

        item['author'] = {
            "name": ig_data['user']['username'],
            "url": 'https://www.instagram.com/' + ig_data['user']['username'],
            "avatar": ig_data['user']['profile_pic_url'],
            "verified": ig_data['user']['is_verified']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

        if ig_data.get('coauthor_producers'):
            for it in ig_data['coauthor_producers']:
                item['authors'].append({
                    "name": it['username'],
                    "url": 'https://www.instagram.com/' + it['username'],
                    "avatar": it['profile_pic_url']
                })
            item['author'] = {
                "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
            }

        image = utils.closest_dict(ig_data['image_versions2']['candidates'], 'width', 640)
        item['image'] = image['url']
        item['_media_aspect_ratio'] = '{}/{}'.format(image['width'], image['height'])

        item['summary'] = re.sub(r'@([^\s]+)', r'<a href="https://www.instagram.com/\1" target="_blank">@\1</a>', ig_data['caption']['text']).replace('\n', '<br/>')

        item['_media'] = []
        if 'reel' in paths or 'reels' in paths:
            item['_video'] = ig_data['video_versions'][0]['url']
            item['_video_type'] = 'video/mp4'
            if ig_data.get('clips_metadata') and ig_data['clips_metadata'].get('original_sound_info'):
                caption = '🎵 ' + ig_data['clips_metadata']['original_sound_info']['ig_artist']['username'] + ' &bull; ' + ig_data['clips_metadata']['original_sound_info']['original_audio_title']
            else:
                caption = ''
            item['_media'].append({"src": item['_video'], "caption": caption, "thumb": item['image'], "video_type": item['_video_type']})
        else:
            src = utils.closest_dict(ig_data['image_versions2']['candidates'], 'width', 2000)['url']
            item['_media'].append({"src": src, "caption": "", "thumb": item['image']})

    format_content(item)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return None