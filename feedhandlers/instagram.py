import json, re, requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit, quote_plus

import config, utils

import logging

logger = logging.getLogger(__name__)


def format_caption_links(matchobj):
    if matchobj.group(1) == '#':
        return '<a href="https://www.instagram.com/explore/tags/{0}/"> #{0}</a>'.format(matchobj.group(2))
    elif matchobj.group(1) == '@':
        return '<a href="https://www.instagram.com/{0}/">@{0}</a>'.format(matchobj.group(2))


def get_content(url, args, site_json, save_debug=False, ig_data=None):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    ig_url = 'https://www.instagram.com/{}/{}/'.format(paths[0], paths[1])
    soup = None
    if not ig_data:
        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "cache-control": "no-cache",
            "dpr": "1",
            "pragma": "no-cache",
            "sec-ch-prefers-color-scheme": "light",
            "sec-ch-ua": "\"Chromium\";v=\"116\", \"Not)A;Brand\";v=\"24\", \"Microsoft Edge\";v=\"116\"",
            "sec-ch-ua-full-version-list": "\"Chromium\";v=\"116.0.5845.97\", \"Not)A;Brand\";v=\"24.0.0.0\", \"Microsoft Edge\";v=\"116.0.1938.54\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-ch-ua-platform-version": "\"15.0.0\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "viewport-width": "993",
            "x-asbd-id": "129477",
            "x-ig-app-id": "936619743392459",
            "x-ig-www-claim": "0",
            "x-requested-with": "XMLHttpRequest",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 Edg/116.0.1938.54"
        }
        gql_url = 'https://www.instagram.com/graphql/query/?doc_id=18222662059122027&variables=%7B%22child_comment_count%22%3A3%2C%22fetch_comment_count%22%3A40%2C%22has_threaded_comments%22%3Atrue%2C%22parent_comment_count%22%3A24%2C%22shortcode%22%3A%22{}%22%7D'.format(paths[1])
        gql_json = utils.get_url_json(gql_url, headers=headers)
        if gql_json:
            #utils.write_file(gql_json, './debug/debug.json')
            ig_data = gql_json['data']['shortcode_media']
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
        utils.write_file(ig_data, './debug/instagram.json')
        if ig_data.get('owner'):
            avatar = '{}/image?url={}&height=48&mask=ellipse'.format(config.server, quote_plus(ig_data['owner']['profile_pic_url']))
            users.append(ig_data['owner']['username'])
            names.append('<br/>' + ig_data['owner']['full_name'])
            if ig_data.get('is_verified'):
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
            post_caption = re.sub(r'(@|#)(\w+)', format_caption_links, post_caption)
            post_caption = '<p>{}</p>'.format(post_caption)

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
    if media_type == 'GraphImage':
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

    elif media_type == 'GraphVideo':
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

    elif media_type == 'GraphSidecar':
        if ig_data:
            for edge in ig_data['edge_sidecar_to_children']['edges']:
                if edge['node']['__typename'] == 'GraphImage':
                    if edge['node'].get('display_resources'):
                        img_src = edge['node']['display_resources'][0]['src']
                    else:
                        img_src = edge['node']['display_url']
                    #post_media += utils.add_image('{}/image?url={}&width=540'.format(config.server, quote_plus(img_src)), height='0', link=img_src, img_style='border-radius:10px;')
                    post_media += '<div><a href="{}"><img src="{}/image?url={}&width=540" style="display:block; width:100%;" /></a></div><div>&nbsp;</div>'.format(img_src, config.server, quote_plus(img_src))

                elif edge['node']['__typename'] == 'GraphVideo':
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
    # For tags there is a json feed at https://www.instagram.com/explore/tags/trending/?__a=1 but it seems to be ip restricted
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "dpr": "1",
        "pragma": "no-cache",
        "sec-ch-prefers-color-scheme": "light",
        "sec-ch-ua": "\"Chromium\";v=\"116\", \"Not)A;Brand\";v=\"24\", \"Microsoft Edge\";v=\"116\"",
        "sec-ch-ua-full-version-list": "\"Chromium\";v=\"116.0.5845.97\", \"Not)A;Brand\";v=\"24.0.0.0\", \"Microsoft Edge\";v=\"116.0.1938.54\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-ch-ua-platform-version": "\"15.0.0\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "viewport-width": "993",
        "x-asbd-id": "129477",
        "x-ig-app-id": "936619743392459",
        "x-ig-www-claim": "0",
        "x-requested-with": "XMLHttpRequest",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 Edg/116.0.1938.54"
    }
    api_url = 'https://www.instagram.com/api/v1/users/web_profile_info/?username={}&hl=en'.format(paths[0])
    s = requests.Session()
    r = s.get(api_url, headers=headers)
    if r.status_code != 200:
        return None
    try:
        user_json = r.json()
    except:
        logger.warning('error getting user data - likely rate-limited')
        return None
    if save_debug:
        utils.write_file(user_json, './debug/feed.json')

    n = 0
    items = []
    feed = utils.init_jsonfeed(args)
    for edge in user_json['data']['user']['edge_owner_to_timeline_media']['edges'] +  user_json['data']['user']['edge_felix_video_timeline']['edges']:
        #edge_url = 'https://www.instagram.com/p/{}/?utm_source=ig_embed&utm_campaign=loading'.format(edge['node']['shortcode'])
        edge_url = 'https://www.instagram.com/p/{}/'.format(edge['node']['shortcode'])
        if save_debug:
            logger.debug('getting content from ' + edge_url)
        edge['node']['owner']['profile_pic_url'] = user_json['data']['user']['profile_pic_url']
        item = get_content(edge_url, args, site_json, save_debug, edge['node'])
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    cookies = s.cookies.get_dict()
    if cookies.get('csrftoken'):
        logger.debug('getting clips')
        headers['x-csrftoken'] = cookies['csrftoken']
        body = {
            "include_feed_video": True,
            "page_size": 12,
            "target_user_id": int(user_json['data']['user']['id'])
        }
        r = s.post('https://www.instagram.com/api/v1/clips/user/?hl=en', json=body, headers=headers)
        if r.status_code == 200:
            try:
                clips_json = r.json()
            except:
                logger.warning('error getting clips data - likely rate-limited')
                return None
            if save_debug:
                utils.write_file(clips_json, './debug/clips.json')
            for clip in clips_json['items']:
                # edge_url = 'https://www.instagram.com/p/{}/?utm_source=ig_embed&utm_campaign=loading'.format(edge['node']['shortcode'])
                clip_url = 'https://www.instagram.com/reel/{}/'.format(clip['media']['code'])
                if save_debug:
                    logger.debug('getting content from ' + clip_url)
                clip['media']['__typename'] = 'GraphVideo'
                item = get_content(clip_url, args, site_json, save_debug, clip['media'])
                if item:
                    if utils.filter_item(item, args) == True:
                        items.append(item)
                        n += 1
                        if 'max' in args:
                            if n == int(args['max']):
                                break
        else:
            logger.warning('error getting clips: ' + r.text)
    feed['items'] = sorted(items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
