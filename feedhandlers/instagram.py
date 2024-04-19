import json, random, re, requests, string
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlencode, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False, ig_data=None):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    ig_url = 'https://www.instagram.com/{}/{}/'.format(paths[-2], paths[-1])
    soup = None
    if not ig_data:
        post_data, profile_data = get_ig_post_data(url, False, save_debug)
        if post_data:
            ig_data = post_data['data']['xdt_shortcode_media']
    if not ig_data:
        logger.debug('using embed data')
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "accept-language": "en-US,en;q=0.9",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "sec-ch-prefers-color-scheme": "dark",
            "sec-ch-ua": "\"Microsoft Edge\";v=\"107\", \"Chromium\";v=\"107\", \"Not=A?Brand\";v=\"24\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 Edg/107.0.1418.35"
        }
        embed_url = ig_url + 'embed/captioned/?cr=1'
        ig_embed = utils.get_url_html(embed_url, headers=headers)
        if not ig_embed:
            return ''
        if save_debug:
            utils.write_file(ig_embed, './debug/instagram.html')

        soup = BeautifulSoup(ig_embed, 'html.parser')
        el = soup.find(class_='EmbedIsBroken')
        if el:
            msg = el.find(class_='ebmMessage').get_text()
            if 'removed' in msg:
                item = {}
                item['content_html'] = '<blockquote><a href="{}">{}</a></blockquote>'.format(ig_url, msg)
                return item
            else:
                logger.warning('embMessage "{}" in {}'.format(el.get_text(), ig_url))
                return None

        m = re.search(r"window\.__additionalDataLoaded\('extra',(.+)\);<\/script>", ig_embed)
        if m:
            try:
                ig_data = json.loads(m.group(1))
            except:
                ig_data = None

        if not ig_data:
            soup = BeautifulSoup(ig_embed, 'html.parser')
            el = soup.find('script', string=re.compile(r'gql_data'))
            if el:
                m = re.search(r'handle\((.*?)\);requireLazy', el.string)
                if m:
                    try:
                        script_data = json.loads(m.group(1))
                        #utils.write_file(script_data, './debug/instagram.json')
                        for data in script_data['require']:
                            if data[0] == 'PolarisEmbedSimple':
                                context_json = json.loads(data[3][0]['contextJSON'])
                                ig_data = context_json['gql_data']
                                break
                    except:
                        ig_data = None

        if ig_data:
            ig_data = ig_data['shortcode_media']

    avatars = []
    users = []
    names = []
    verified = []
    if ig_data:
        if save_debug:
            utils.write_file(ig_data, './debug/instagram.json')
        if ig_data.get('owner'):
            avatar = '{}/image?url={}&height=48&mask=ellipse'.format(config.server, quote_plus(ig_data['owner']['profile_pic_url']))
            users.append(ig_data['owner']['username'])
            if ig_data['owner'].get('full_name'):
                names.append('<br/>' + ig_data['owner']['full_name'])
            else:
                names.append('')
            if ig_data['owner'].get('is_verified'):
                verified.append(' &#9989;')
            else:
                verified.append('')
        elif ig_data.get('user'):
            avatar = '{}/image?url={}&height=48&mask=ellipse'.format(config.server, quote_plus(ig_data['user']['profile_pic_url']))
            users.append(ig_data['user']['username'])
            names.append('')
            verified.append('')
        avatars.append(avatar)
    else:
        el = soup.find(class_='Avatar')
        if el:
            avatar = '{}/image?url={}&height=48&mask=ellipse'.format(config.server, quote_plus(el.img['src']))
            avatars.append(avatar)
            users.append(soup.find(class_='UsernameText').get_text())
            names.append('')
            verified.append('')
        else:
            for el in soup.find_all(class_='CollabAvatar'):
                avatar = '{}/image?url={}&height=48&mask=ellipse'.format(config.server, quote_plus(el.img['src']))
                avatars.append(avatar)
                m = re.search(r'^/([^/]+)/', urlsplit(el['href']).path)
                if m:
                    users.append(m.group(1))
                    names.append('')
                    verified.append('')

    username = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(users))
    title = '{} posted on Instagram'.format(username)

    item = {}
    item['id'] = ig_url
    item['url'] = ig_url
    if len(title) > 50:
        item['title'] = title[:50] + '...'
    else:
        item['title'] = title
    if ig_data:
        if ig_data.get('taken_at_timestamp'):
            # Assuming it's UTC
            dt = datetime.fromtimestamp(ig_data['taken_at_timestamp']).replace(tzinfo=timezone.utc)
        elif ig_data.get('taken_at'):
            dt = datetime.fromtimestamp(ig_data['taken_at']).replace(tzinfo=timezone.utc)
        else:
            dt = None
        if dt:
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)
    item['author'] = {}
    item['author']['name'] = username

    if ig_data.get('display_url'):
        item['_image'] = ig_data['display_url']

    tags = []

    post_caption = ''
    if ig_data:
        if ig_data.get('caption'):
            post_caption = ig_data['caption']['text']
        else:
            try:
                post_caption = ig_data['edge_media_to_caption']['edges'][0]['node']['text']
            except:
                post_caption = None
        if post_caption:
            post_caption = post_caption.replace('\n', '<br/>')
            def format_caption_links(matchobj):
                nonlocal tags
                if matchobj.group(1) == '#':
                    tags.append(matchobj.group(2))
                    return '<a href="https://www.instagram.com/explore/tags/{}/"> #{}</a>'.format(matchobj.group(2).lower(), matchobj.group(2))
                elif matchobj.group(1) == '@':
                    return '<a href="https://www.instagram.com/{0}/">@{0}</a>'.format(matchobj.group(2))
            post_caption = re.sub(r'(@|#)(\w+)', format_caption_links, post_caption)
            post_caption = '<p>{}</p>'.format(post_caption)

    if len(tags) > 0:
        item['tags'] = tags.copy()

    if soup and not post_caption:
        caption = soup.find(class_='Caption')
        if caption:
            # Make paragragh instead of div to help with spacing
            caption.name = 'p'
            caption.attrs = {}

            # Remove username from beginning of caption
            el = caption.find('a', class_='CaptionUsername')
            if el and el.get_text() == username:
                el.decompose()

            # Remove comment section
            el = caption.find(class_='CaptionComments')
            if el:
                el.decompose()

            # Remove whitespace from start
            while caption.contents[0] == '\n' or caption.contents[0].name == 'br':
                caption.contents.pop(0)

            # Fix links
            for a in caption.find_all('a'):
                split_url = urlsplit(a['href'])
                if split_url.scheme:
                    a_href = '{}://{}{}'.format(split_url.scheme, split_url.netloc, split_url.path)
                else:
                    a_href = 'https://www.instagram.com' + split_url.path
                a.attrs = {}
                a['href'] = a_href
                a['style'] = 'text-decoration:none;'
                a.string = a.get_text()

            if str(caption):
                title = '{} posted: {}'.format(username, caption.get_text())
                post_caption = str(caption)
            while post_caption.startswith('<br/>'):
                post_caption = post_caption[5:]

    post_media = ''
    if ig_data:
        media_type = ig_data['__typename']
    else:
        media_type = soup.find(class_='Embed')['data-media-type']
    if media_type == 'GraphImage' or media_type == 'XDTGraphImage':
        if ig_data:
            if ig_data.get('display_resources'):
                img_src = ig_data['display_resources'][0]['src']
            else:
                img_src = ig_data['display_url']
            #post_media += utils.add_image('{}/image?url={}&width=540'.format(config.server, quote_plus(img_src)), height='0', link=img_src, img_style='border-radius:10px;')
            post_media += '<div><a href="{}"><img src="{}/image?url={}&width=540" style="display:block; width:100%;" /></a></div><div>&nbsp;</div>'.format(img_src, config.server, quote_plus(img_src))
        else:
            for el in soup.find_all('img', class_='EmbeddedMediaImage'):
                if el.has_attr('srcset'):
                    img_src = utils.image_from_srcset(el['srcset'], 640)
                else:
                    img_src = el['src']
                #post_media += utils.add_image('{}/image?url={}&width=540'.format(config.server, quote_plus(img_src)), height='0', link=img_src, img_style='border-radius:10px;')
                post_media += '<div><a href="{}"><img src="{}/image?url={}&width=540" style="display:block; width:100%;" /></a></div><div>&nbsp;</div>'.format(img_src, config.server, quote_plus(img_src))

    elif media_type == 'GraphVideo' or media_type == 'XDTGraphVideo':
        if ig_data:
            if ig_data.get('video_versions'):
                video_src = ig_data['video_versions'][0]['url']
            else:
                video_src = ig_data['video_url']
            if ig_data.get('display_resources'):
                img = utils.closest_dict(ig_data['display_resources'], 'config_width', 640)
                img_src = img['src']
            elif ig_data.get('image_versions2'):
                img = utils.closest_dict(ig_data['image_versions2']['candidates'], 'width', 640)
                img_src = img['url']
            else:
                img_src = ig_data['display_url']
            #post_media += utils.add_image('{}/image?url={}&width=540&overlay=video'.format(config.server, quote_plus(img_src)), height='0', link=video_src, img_style='border-radius:10px;')
            post_media += '<div><a href="{}"><img src="{}/image?url={}&width=540&overlay=video" style="display:block; width:100%;" /></a></div><div>&nbsp;</div>'.format(video_src, config.server, quote_plus(img_src))
        else:
            el = soup.find('img', class_='EmbeddedMediaImage')
            if el:
                img_src = el['src']
                poster = '{}/image?url={}&width=540&overlay=video'.format(config.server, quote_plus(img_src))
                caption = '<div style="padding:0 8px 0 8px;"><small><a href="{}">Watch on Instagram</a></small></div>'.format(ig_url)
                #post_media += utils.add_image(poster, caption, height='0', link=ig_url, img_style='border-radius:10px;')
                post_media += '<div><a href="{}"><img src="{}/image?url={}&width=540&overlay=video" style="display:block; width:100%;" /></a></div>{}<div>&nbsp;</div>'.format(ig_url, config.server, quote_plus(img_src), caption)

    elif media_type == 'GraphSidecar' or media_type == 'XDTGraphSidecar':
        if ig_data:
            for edge in ig_data['edge_sidecar_to_children']['edges']:
                if edge['node']['__typename'] == 'GraphImage' or edge['node']['__typename'] == 'XDTGraphImage':
                    if edge['node'].get('display_resources'):
                        img_src = edge['node']['display_resources'][0]['src']
                    else:
                        img_src = edge['node']['display_url']
                    #post_media += utils.add_image('{}/image?url={}&width=540'.format(config.server, quote_plus(img_src)), height='0', link=img_src, img_style='border-radius:10px;')
                    post_media += '<div><a href="{}"><img src="{}/image?url={}&width=540" style="display:block; width:100%;" /></a></div><div>&nbsp;</div>'.format(img_src, config.server, quote_plus(img_src))

                elif edge['node']['__typename'] == 'GraphVideo' or edge['node']['__typename'] == 'XDTGraphVideo':
                    if edge['node'].get('video_url'):
                        video_src = edge['node']['video_url']
                        caption = ''
                    else:
                        video_src = ''
                        #caption = '<a href="{}"><small>Watch on Instagram</small></a>'.format(ig_url)
                        caption = '<div style="padding:0 8px 0 8px;"><small><a href="">{}>Watch on Instagram</a></small></div>'.format(ig_url)
                    if edge['node'].get('display_resources'):
                        img = utils.closest_dict(edge['node']['display_resources'], 'config_width', 640)
                        img_src = img['src']
                    else:
                        img_src = edge['node']['display_url']
                    #post_media += utils.add_image('{}/image?url={}&width=540&overlay=video'.format(config.server, quote_plus(img_src)), caption, height='0', link=video_src, img_style='border-radius:10px;')
                    post_media += '<div><a href="{}"><img src="{}/image?url={}&width=540&overlay=video" style="display:block; width:100%;" /></a></div>{}<div>&nbsp;</div>'.format(video_src, config.server, quote_plus(img_src), caption)
                #post_media += '<div>&nbsp;</div>'
            #post_media = post_media[:-10]
        else:
            logger.warning('Instagram GraphSidecar media without ig_data in ' + ig_url)
    post_media = re.sub('<div>&nbsp;</div>$', '', post_media)

    #item['content_html'] = '<div style="width:488px; padding:8px 0 8px 8px; border:1px solid black; border-radius:10px; font-family:Roboto,Helvetica,Arial,sans-serif;"><div><img style="float:left; margin-right:8px;" src="{0}"/><span style="line-height:48px; vertical-align:middle;"><a href="https://www.instagram.com/{1}"><b>{1}</b></a></span></div><br/><div style="clear:left;"></div>'.format(avatar, username)
    #item['content_html'] = '<table style="table-layout:fixed; width:90%; max-width:496px; margin-left:auto; margin-right:auto; border:1px solid black; border-radius:10px; font-family:Roboto,Helvetica,Arial,sans-serif;">'
    item['content_html'] = '<table style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0; border:1px solid black; border-collapse:collapse;">'
    for i in range(len(users)):
        if i == 0:
            item['content_html'] += '<tr><td style="width:48px; padding:8px;"><img src="{0}"/></td><td style="text-align:left; vertical-align:middle;"><a href="https://www.instagram.com/{1}"><b>{1}</b></a>{2}{3}</td><td style="width:48px; text-align:center; verticla-align:middle;"><a href="{4}"><img src="https://static.cdninstagram.com/rsrc.php/v3/yI/r/VsNE-OHk_8a.png"/></a></tr>'.format(avatars[i], users[i], verified[i], names[i], item['url'])
        else:
            item['content_html'] += '<tr><td style="width:48px; padding:8px;"><img src="{0}"/></td><td colspan="2" style="text-align:left; vertical-align:middle;"><a href="https://www.instagram.com/{1}"><b>{1}</b></a>{2}{3}</td></tr>'.format(avatars[i], users[i], verified[i], names[i])

    item['content_html'] += '<tr><td colspan="3" style="padding:0;">'
    if post_media:
        item['content_html'] += post_media
    item['content_html'] += '</td></tr>'

    item['content_html'] += '<tr><td colspan="3" style="padding:8px; word-wrap:break-word;">{}</td></tr>'.format(post_caption)

    item['content_html'] += '<tr><td colspan="3" style="padding:8px;">'
    if item.get('_display_date'):
        item['content_html'] += '<a href="{}"><small>{}</small></a>'.format(item['url'], item['_display_date'])
    else:
        item['content_html'] += '<a href="{}"><small>Open in Instagram</small></a>'.format(item['url'])
    item['content_html'] += '</td></tr></table>'
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if not site_json['profile'].get(paths[0]):
        logger.warning('unable to get user profile posts without an existing post url')
        return None
    post_data, profile_data = get_ig_post_data(site_json['profile'][paths[0]], True, save_debug)
    if not profile_data:
        return None
    # # For tags there is a json feed at https://www.instagram.com/explore/tags/trending/?__a=1 but it seems to be ip restricted
    # split_url = urlsplit(url)
    # paths = list(filter(None, split_url.path.split('/')))
    #
    # headers = {
    #     "accept": "*/*",
    #     "accept-language": "en-US,en;q=0.9",
    #     "cache-control": "no-cache",
    #     "dpr": "1",
    #     "pragma": "no-cache",
    #     "sec-ch-prefers-color-scheme": "light",
    #     "sec-ch-ua": "\"Chromium\";v=\"116\", \"Not)A;Brand\";v=\"24\", \"Microsoft Edge\";v=\"116\"",
    #     "sec-ch-ua-full-version-list": "\"Chromium\";v=\"116.0.5845.97\", \"Not)A;Brand\";v=\"24.0.0.0\", \"Microsoft Edge\";v=\"116.0.1938.54\"",
    #     "sec-ch-ua-mobile": "?0",
    #     "sec-ch-ua-platform": "\"Windows\"",
    #     "sec-ch-ua-platform-version": "\"15.0.0\"",
    #     "sec-fetch-dest": "empty",
    #     "sec-fetch-mode": "cors",
    #     "sec-fetch-site": "same-origin",
    #     "viewport-width": "993",
    #     "x-asbd-id": "129477",
    #     "x-ig-app-id": "936619743392459",
    #     "x-ig-www-claim": "0",
    #     "x-requested-with": "XMLHttpRequest",
    #     "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 Edg/116.0.1938.54"
    # }
    # api_url = 'https://www.instagram.com/api/v1/users/web_profile_info/?username={}&hl=en'.format(paths[0])
    # s = requests.Session()
    # r = s.get(api_url, headers=headers)
    # if r.status_code != 200:
    #     return None
    # try:
    #     ig_data = r.json()
    # except:
    #     logger.warning('error getting user data - likely rate-limited')
    #     return None
    # if save_debug:
    #     utils.write_file(ig_data, './debug/feed.json')

    n = 0
    items = []
    feed = utils.init_jsonfeed(args)
    # for edge in ig_data['data']['user']['edge_owner_to_timeline_media']['edges'] +  ig_data['data']['user']['edge_felix_video_timeline']['edges']:
    for edge in profile_data['data']['user']['edge_owner_to_timeline_media']['edges']:
        #edge_url = 'https://www.instagram.com/p/{}/?utm_source=ig_embed&utm_campaign=loading'.format(edge['node']['shortcode'])
        if edge['node']['__typename'] == 'GraphVideo':
            edge_url = 'https://www.instagram.com/reel/{}/'.format(edge['node']['shortcode'])
        else:
            edge_url = 'https://www.instagram.com/p/{}/'.format(edge['node']['shortcode'])
        if save_debug:
            logger.debug('getting content from ' + edge_url)
        # edge['node']['owner']['profile_pic_url'] = post_data['data']['xdt_shortcode_media']['owner']['profile_pic_url']
        edge['node']['owner'] = post_data['data']['xdt_shortcode_media']['owner']
        item = get_content(edge_url, args, site_json, save_debug, edge['node'])
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    # cookies = s.cookies.get_dict()
    # if cookies.get('csrftoken'):
    #     logger.debug('getting clips')
    #     headers['x-csrftoken'] = cookies['csrftoken']
    #     body = {
    #         "include_feed_video": True,
    #         "page_size": 12,
    #         "target_user_id": int(user_json['data']['user']['id'])
    #     }
    #     r = s.post('https://www.instagram.com/api/v1/clips/user/?hl=en', json=body, headers=headers)
    #     if r.status_code == 200:
    #         try:
    #             clips_json = r.json()
    #         except:
    #             logger.warning('error getting clips data - likely rate-limited')
    #             return None
    #         if save_debug:
    #             utils.write_file(clips_json, './debug/clips.json')
    #         for clip in clips_json['items']:
    #             # edge_url = 'https://www.instagram.com/p/{}/?utm_source=ig_embed&utm_campaign=loading'.format(edge['node']['shortcode'])
    #             clip_url = 'https://www.instagram.com/reel/{}/'.format(clip['media']['code'])
    #             if save_debug:
    #                 logger.debug('getting content from ' + clip_url)
    #             clip['media']['__typename'] = 'GraphVideo'
    #             item = get_content(clip_url, args, site_json, save_debug, clip['media'])
    #             if item:
    #                 if utils.filter_item(item, args) == True:
    #                     items.append(item)
    #                     n += 1
    #                     if 'max' in args:
    #                         if n == int(args['max']):
    #                             break
    #     else:
    #         logger.warning('error getting clips: ' + r.text)
    feed['items'] = sorted(items, key=lambda i: i['_timestamp'], reverse=True)
    return feed


# https://github.com/Ximaz/instagram-api/blob/0b40c040cf5f1da08071e43b7ff8e753e71a73ea/apigram/natives.py
def get_ig_post_data(url, get_profile_posts=False, save_debug=False, load_from_file=False):
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "dpr": "1",
        "pragma": "no-cache",
        "sec-ch-prefers-color-scheme": "light",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"123\", \"Not:A-Brand\";v=\"8\", \"Chromium\";v=\"123\"",
        "sec-ch-ua-full-version-list": "\"Microsoft Edge\";v=\"123.0.2420.65\", \"Not:A-Brand\";v=\"8.0.0.0\", \"Chromium\";v=\"123.0.6312.87\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-model": "\"\"",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-ch-ua-platform-version": "\"15.0.0\"",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "viewport-width": "852",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0"
    }

    s = curl_requests.Session(impersonate='chrome116')
    r = s.get(utils.clean_url(url), proxies=config.proxies)
    if r.status_code != 200:
        return None
    page_html = r.text

    if load_from_file:
        page_html = utils.read_file('./debug/instagram.html')
        web_session_id = '3hn9qf:77mmtq:efs8ue'
    else:
        if save_debug:
            utils.write_file(page_html, './debug/instagram.html')
        # web_session_id = rand_str(6) + ':' + rand_str(6) + ':' + rand_str(6)
        web_session_id = ':' + rand_str(6) + ':' + rand_str(6)

    page_soup = BeautifulSoup(page_html, 'lxml')

    csr_bm = []
    dyn_bm = []
    site_data = None
    polaris_site_data = None
    user_data = None
    config_defaults = None
    eqmc_params = None
    deferred_cookies = None
    preloaders = None
    csrf_token = ''
    lsd_token = ''
    shortcode = ''
    owner_id = ''
    versioning_id = ''
    machine_id = ''
    device_id = ''

    for el in page_soup.find_all('script', attrs={"type": "application/json"}):
        script_json = json.loads(el.string)
        if el.get('id') and el['id'] == '__eqmc':
            if script_json.get('u'):
                eqmc_params = parse_qs(urlsplit(script_json['u']).query)
        elif script_json.get('require'):
            for it in script_json['require']:
                if it[0] == 'Bootloader' and it[1] and it[1] == 'handlePayload':
                    for data in it[3]:
                        if data.get('rsrcMap'):
                            for key, val in data['rsrcMap'].items():
                                if val.get('src') and val['src'].startswith('https'):
                                    for p in val['p'].replace(':', '').split(','):
                                        bm_set_value(csr_bm, int(p))
                elif it[0] == 'ScheduledServerJS' and it[1] and it[1] == 'handle':
                    for data in it[3]:
                        if data.get('__bbox'):
                            if data['__bbox'].get('define'):
                                for d in data['__bbox']['define']:
                                    if d[0] == 'SiteData':
                                        site_data = d[2]
                                    elif d[0] == 'PolarisSiteData':
                                        polaris_site_data = d[2]
                                    elif d[0] == 'CurrentUserInitialData':
                                        user_data = d[2]
                                    elif d[0] == 'RelayAPIConfigDefaults':
                                        config_defaults = d[2]
                                    elif d[0] == 'InstagramSecurityConfig' and d[2].get('csrf_token'):
                                        csrf_token = d[2]['csrf_token']
                                    elif d[0] == 'LSD' and d[2].get('token'):
                                        lsd_token = d[2]['token']
                                    elif d[0] == 'WebBloksVersioningID' and d[2].get('versioningID'):
                                        versioning_id = d[2]['versioningID']
                                    elif d[0] == 'BarcelonaSharedData' and d[2].get('machine_id'):
                                        machine_id = d[2]['machine_id']
                                    elif d[0] == 'AnalyticsCoreData' and d[2].get('device_id'):
                                        device_id = d[2]['device_id'].split('|')[-1]
                                    if len(d) == 4 and isinstance(d[3], int) and d[3] > 0:
                                        bm_set_value(dyn_bm, d[3])
                            if data['__bbox'].get('require'):
                                for d in data['__bbox']['require']:
                                    if d[0].startswith('CometPlatformRootClient') and d[1]:
                                        if d[1] == 'setInitDeferredPayload':
                                            for x in d[3]:
                                                if isinstance(x, dict) and x.get('deferredCookies'):
                                                    deferred_cookies = x['deferredCookies']
                                        elif d[1] == 'init':
                                            for x in d[3]:
                                                if isinstance(x, dict):
                                                    if x.get('params'):
                                                        shortcode = x['params']['shortcode']
                                                    if x.get('rootView'):
                                                        owner_id = x['rootView']['props']['page_logging']['params']['owner_id']
                                        elif d[1] == 'initialize':
                                            for x in d[3]:
                                                if isinstance(x, dict):
                                                    if x.get('expectedPreloaders'):
                                                        preloaders = x['expectedPreloaders'][0]
                                                    if x.get('initialRouteInfo') and x['initialRouteInfo'].get('route'):
                                                        if x['initialRouteInfo']['route'].get('params') and x['initialRouteInfo']['route']['params'].get('shortcode'):
                                                            shortcode = x['initialRouteInfo']['route']['params']['shortcode']
                                                        if x['initialRouteInfo']['route'].get('rootView') and x['initialRouteInfo']['route']['rootView'].get('props') and x['initialRouteInfo']['route']['rootView']['props'].get('page_logging') and x['initialRouteInfo']['route']['rootView']['props']['page_logging'].get('params') and x['initialRouteInfo']['route']['rootView']['props']['page_logging']['params'].get('owner_id'):
                                                            owner_id = x['initialRouteInfo']['route']['rootView']['props']['page_logging']['params']['owner_id']
    for el in page_soup.find_all('link', attrs={"data-bootloader-hash": True, "data-p": True}):
        if el.get('href') and el['href'].startswith('https'):
            for p in el['data-p'].replace(':', '').split(','):
                bm_set_value(csr_bm, int(p))

    for el in page_soup.find_all('script', attrs={"data-bootloader-hash": True, "data-p": True}):
        if el.get('src') and el['src'].startswith('https'):
            for p in el['data-p'].replace(':', '').split(','):
                bm_set_value(csr_bm, int(p))

    if not site_data:
        logger.warning('unable to find SiteData in ' + url)
    if not user_data:
        logger.warning('unable to find CurrentUserInitialData in ' + url)
    if not config_defaults:
        logger.warning('unable to find RelayAPIConfigDefaults in ' + url)
    if not csrf_token:
        logger.warning('unable to find csrf_token in ' + url)
    if not eqmc_params:
        logger.warning('unable to find eqmc data in ' + url)
    if not csr_bm:
        logger.warning('unable to get CSR BitMap data in ' + url)
    if not dyn_bm:
        logger.warning('unable to get ServerJS BitMap data in ' + url)
    if not (site_data or user_data or config_defaults or csrf_token or eqmc_params or csr_bm or dyn_bm):
        return None

    post_doc_id = ''
    profile_doc_id = ''
    asbd_id = ''
    for el in page_soup.find_all('link', href=re.compile(r'https://static\.cdninstagram\.com/rsrc\.php/.*\.js')):
        # print(el['href'])
        r = s.get(el['href'], proxies=config.proxies)
        if r.status_code == 200:
            if 'instagram.com' in url:
                m = re.search(r'"PolarisPostActionLoadPostQueryQuery_instagramRelayOperation".*?="(\d+)"', r.text)
                if m:
                    post_doc_id = m.group(1)
                m = re.search(r'"PolarisProfilePostsActions".*?="(\d+)"', r.text)
                if m:
                    profile_doc_id = m.group(1)
            elif 'threads.net' in url:
                m = re.search(r'"BarcelonaPostPage__data".*?id:"(\d+)"', r.text)
                if m:
                    post_doc_id = m.group(1)
            m = re.search(r'a="(\d+)";f\.ASBD_ID=a', r.text)
            if m:
                asbd_id = m.group(1)
    if not post_doc_id:
        logger.warning('unable to determine post_doc_id in ' + url)
    if not asbd_id:
        logger.warning('unable to determine asbd_id in ' + url)
    if not post_doc_id or not asbd_id:
        return None

    post_data = None
    profile_data = None

    if 'instagram.com' in url:
        gql_url = 'https://www.instagram.com/graphql/query'
        req_friendly_name = 'PolarisPostActionLoadPostQueryQuery'
        variables = {
            "shortcode": shortcode,
            "fetch_comment_count": 40,
            "fetch_related_profile_media_count": 3,
            "parent_comment_count": 24,
            "child_comment_count": 3,
            "fetch_like_count": 10,
            "fetch_tagged_user_count": None,
            "fetch_preview_comment_count": 2,
            "has_threaded_comments": True,
            "hoisted_comment_id": None,
            "hoisted_reply_id": None
        }
    elif 'threads.net' in url:
        gql_url = 'https://www.threads.net/api/graphql'
        req_friendly_name = 'BarcelonaPostPageQuery'
        if preloaders and preloaders.get('variables'):
            variables = preloaders['variables']
        else:
            variables = {
                "postID": "3313208983259045191",
                "__relay_internal__pv__BarcelonaIsLoggedInrelayprovider": False,
                "__relay_internal__pv__BarcelonaIsThreadContextHeaderEnabledrelayprovider": False,
                "__relay_internal__pv__BarcelonaIsThreadContextHeaderFollowButtonEnabledrelayprovider": False,
                "__relay_internal__pv__BarcelonaUseCometVideoPlaybackEnginerelayprovider": False,
                "__relay_internal__pv__BarcelonaOptionalCookiesEnabledrelayprovider": True,
                "__relay_internal__pv__BarcelonaIsViewCountEnabledrelayprovider": False,
                "__relay_internal__pv__BarcelonaShouldShowFediverseM075Featuresrelayprovider": False
            }

    gql_cookies = {}
    if s.cookies and not load_from_file:
        for key, val in s.cookies.items():
            gql_cookies[key] = val
    if not gql_cookies.get('csrftoken'):
        gql_cookies['csrftoken'] = csrf_token
    if not gql_cookies.get('ig_did'):
        if deferred_cookies and deferred_cookies.get('_js_ig_did'):
            gql_cookies['ig_did'] = deferred_cookies['_js_ig_did']['value']
        elif polaris_site_data and polaris_site_data.get('device_id'):
            gql_cookies['ig_did'] = polaris_site_data['device_id']
        elif device_id:
            gql_cookies['ig_did'] = device_id
    if not gql_cookies.get('datr'):
        if deferred_cookies and deferred_cookies.get('_js_datr'):
            gql_cookies['datr'] = deferred_cookies['_js_datr']['value']
    if not gql_cookies.get('mid'):
        if deferred_cookies and deferred_cookies.get('mid'):
            gql_cookies['mid'] = deferred_cookies['mid']['value']
        elif polaris_site_data and polaris_site_data['machine_id']:
            gql_cookies['mid'] = polaris_site_data['machine_id']
        elif machine_id:
            gql_cookies['mid'] = machine_id
    if not gql_cookies.get('ps_l'):
        gql_cookies['ps_l'] = "0"
    if not gql_cookies.get('ps_n'):
        gql_cookies['ps_n'] = "0"
    if not gql_cookies.get('ig_nrcb'):
        gql_cookies['ig_nrcb'] = "1"

    gql_headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/x-www-form-urlencoded",
        "cookie": '; '.join(['{}={}'.format(k, v) for k, v in gql_cookies.items()]),
        "dpr": "1",
        "sec-ch-prefers-color-scheme": "light",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"123\", \"Not:A-Brand\";v=\"8\", \"Chromium\";v=\"123\"",
        "sec-ch-ua-full-version-list": "\"Microsoft Edge\";v=\"123.0.2420.65\", \"Not:A-Brand\";v=\"8.0.0.0\", \"Chromium\";v=\"123.0.6312.87\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-model": "\"\"",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-ch-ua-platform-version": "\"15.0.0\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
        "viewport-width": "852",
        "x-asbd-id": asbd_id,
        "x-bloks-version-id": versioning_id,
        "x-csrftoken": csrf_token,
        "x-fb-friendly-name": req_friendly_name,
        "x-fb-lsd": lsd_token,
        "x-ig-app-id": config_defaults['customHeaders']['X-IG-App-ID']
    }

    gql_data = {
        "av": 0,
        "__d": "",
        "__user": eqmc_params['__user'][0],
        "__a": eqmc_params['__a'][0],
        "__req": hex(random.randint(1, 15))[2:],
        "__hs": site_data['haste_session'],
        "dpr": site_data['pr'],
        "__ccg": "UNKNOWN",
        "__rev": site_data['client_revision'],
        "__s": web_session_id,
        "__hsi": site_data['hsi'],
        "__dyn": to_compressed_string(dyn_bm),
        "__csr": to_compressed_string(csr_bm),
        "__comet_req": eqmc_params['__comet_req'][0],
        "lsd": lsd_token,
        "jazoest": eqmc_params['jazoest'][0],
        "__spin_r": site_data['__spin_r'],
        "__spin_b": site_data['__spin_b'],
        "__spin_t": site_data['__spin_t'],
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": req_friendly_name,
        "server_timestamps": True,
        "doc_id": post_doc_id
    }
    if config_defaults['customHeaders'].get('X-IG-D'):
        gql_data['__d'] = config_defaults['customHeaders']['X-IG-D']
    else:
        del gql_data['__d']

    body = urlencode(gql_data) + '&variables=' + quote_plus(json.dumps(variables, separators=(',', ':')))

    # print(json.dumps(gql_cookies, indent=4))
    # print(json.dumps(gql_headers, indent=4))
    # print(json.dumps(gql_data, indent=4))
    # print(json.dumps(variables, indent=4))
    # print(body)

    # r = requests.post(gql_url, data=body, headers=gql_headers, proxies=config.proxies)
    # r = curl_requests.post(gql_url, data=body, impersonate='chrome116', headers=gql_headers, proxies=config.proxies)
    r = s.post(gql_url, data=body, headers=gql_headers, proxies=config.proxies)
    if r.status_code == 200:
        try:
            post_data = r.json()
            if save_debug:
                utils.write_file(post_data, './debug/instagram.json')
        except:
            logger.warning('error converting {} to json: {}'.format(req_friendly_name, r.text))
    else:
        logger.warning('status code {} getting {}'.format(req_friendly_name, r.status_code))

    if post_data and get_profile_posts:
        gql_url = 'https://www.instagram.com/graphql/query/?doc_id={}&variables=%7B%22id%22%3A%22{}%22%2C%22first%22%3A12%7D'.format(profile_doc_id, owner_id)
        gql_headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "cookie": '; '.join(['{}={}'.format(k, v) for k, v in gql_cookies.items()]),
            "dpr": "1",
            "sec-ch-prefers-color-scheme": "light",
            "sec-ch-ua": "\"Microsoft Edge\";v=\"123\", \"Not:A-Brand\";v=\"8\", \"Chromium\";v=\"123\"",
            "sec-ch-ua-full-version-list": "\"Microsoft Edge\";v=\"123.0.2420.81\", \"Not:A-Brand\";v=\"8.0.0.0\", \"Chromium\";v=\"123.0.6312.106\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-model": "\"\"",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-ch-ua-platform-version": "\"15.0.0\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "viewport-width": "1113",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
            "x-asbd-id": asbd_id,
            "x-csrftoken": csrf_token,
            "x-ig-app-id": config_defaults['customHeaders']['X-IG-App-ID'],
            "x-ig-www-claim": "0",
            "x-requested-with": "XMLHttpRequest"
        }
        print(gql_url)
        print(json.dumps(gql_headers, indent=4))
        # r = requests.get(gql_url, headers=gql_headers, proxies=config.proxies)
        r = s.get(gql_url, headers=gql_headers, proxies=config.proxies)
        if r.status_code == 200:
            try:
                profile_data = r.json()
                if save_debug:
                    utils.write_file(profile_data, './debug/ig_profile.json')
            except:
                logger.warning('error converting profile query to json: ' + r.text)
        else:
            logger.warning('status code {} getting profile query'.format(r.status_code))
    return post_data, profile_data



def bm_set_value(b_map, i):
    n = len(b_map)
    if i < n:
        b_map[i] = 1
    else:
        for j in range(n, i):
            b_map.append(0)
        b_map.append(1)
    return b_map


def to_compressed_string(bm):
    buf = []
    count = 1
    last_val = bm[0]
    d = bin(last_val)[2:]
    for i in range(1, len(bm)):
        cur_val = bm[i]
        if cur_val == last_val:
            count += 1
        else:
            buf.append(encode_run_length(count))
            last_val = cur_val
            count = 1
    if count:
        buf.append(encode_run_length(count))
    comp_str = encode_base64(d + ''.join(buf))
    return comp_str


def encode_run_length(num):
    a = bin(num)[2:]
    b = '0' * (len(a) - 1)
    return b + a


def encode_base64(binary_str):
    char_map = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_'
    encoded_str = ''
    for b in re.findall(r'[01]{6}', binary_str + '00000'):
        encoded_str += char_map[int(b, 2)]
    return encoded_str


def rand_str(n):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))
