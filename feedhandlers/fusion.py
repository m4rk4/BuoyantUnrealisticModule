import base64, hashlib, hmac, json, math, pytz, random, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit, unquote_plus, quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_deployment_value(url):
    page_html = utils.get_url_html(url)
    if page_html:
        m = re.search(r'Fusion\.deployment="(\d+)"', page_html)
        if m:
            return int(m.group(1))
        else:
            m = re.search(r'"arcVersion":"(\d+)"', page_html)
            if m:
                return int(m.group(1))
    return -1


def resize_image(image_item, site_json, width=1280):
    img_src = ''
    if image_item.get('url') and 'washpost' in image_item['url']:
        if width == 1280:
            width = 916
        img_src = 'https://www.washingtonpost.com/wp-apps/imrs.php?src={}&w={}'.format(quote_plus(image_item['url']), width)
    elif site_json.get('resize_image'):
        query = re.sub(r'\s', '', json.dumps(site_json['resize_image']['query'])).replace('SRC', image_item['url'])
        api_url = '{}{}?query={}&d={}&_website={}'.format(site_json['api_url'], site_json['resize_image']['source'], quote_plus(query), site_json['deployment'], site_json['arc_site'])
        api_json = utils.get_url_json(api_url)
        if api_json:
            images = []
            for key, val in api_json.items():
                m = re.search(r'(\d+)x(\d+)', key)
                if m and m.group(2) == '0':
                    img = {
                        "width": int(m.group(1)),
                        "path": val.replace('=filters:', '=/{}/filters:'.format(key))
                    }
                    images.append(img)
            if images:
                split_url = urlsplit(image_item['url'])
                img = utils.closest_dict(images, 'width', width)
                img_src = site_json['resizer_url'] + img['path'] + split_url.netloc + split_url.path
    elif site_json.get('resizer_secret'):
        split_url = urlsplit(image_item['url'])
        if split_url.path.startswith('/resizer'):
            m = re.search(r'/([^/]+(advancelocal|arcpublishing).*)', split_url.path)
            if not m:
                logger.warning('unable to determine image path in ' + image_item['url'])
                return image_item['url']
            image_path = m.group(1)
        else:
            image_path = '{}{}'.format(split_url.netloc, split_url.path)
        operation_path = '{}x0/smart/'.format(width)
        # THUMBOR_SECURITY_KEY (from tampabay.com)
        #security_key = 'Fmkgru2rZ2uPZ5wXs7B2HbVDHS2SZuA7'
        hashed = hmac.new(bytes(site_json['resizer_secret'], 'ascii'), bytes(operation_path+image_path, 'ascii'), hashlib.sha1)
        #resizer_hash = base64.b64encode(hashed.digest()).decode().replace('+', '-').replace('/', '_')
        resizer_hash = base64.urlsafe_b64encode(hashed.digest()).decode()
        img_src = '{}{}/{}{}'.format(site_json['resizer_url'], resizer_hash, operation_path, image_path)
    elif '/gmg/' in image_item['url']:
        split_url = urlsplit(image_item['url'])
        paths = list(filter(None, split_url.path[1:].split('/')))
        img_src = 'https://res.cloudinary.com/graham-media-group/image/upload/f_auto/q_auto/c_scale,w_{}/v1/media/gmg/{}?_a=DAJAUVWIZAAA'.format(width, paths[-1])
    elif site_json.get('resizer_url') and ((image_item.get('additional_properties') and (image_item['additional_properties'].get('fullSizeResizeUrl') or image_item['additional_properties'].get('thumbnailResizeUrl') or image_item['additional_properties'].get('resizeUrl'))) or image_item.get('imageWebUrl') or image_item.get('resizer_url')):
        for key in ['additional_properties/fullSizeResizeUrl', 'additional_properties/thumbnailResizeUrl', 'additional_properties/resizeUrl', 'imageWebUrl', 'resizer_url']:
            keys = key.split('/')
            if len(keys) == 2 and image_item.get(keys[0]) and image_item[keys[0]].get(keys[1]):
                src = image_item[keys[0]][keys[1]]
            elif len(keys) == 1 and image_item.get(key):
                src = image_item[key]
            else:
                src = ''
            if src:
                split_url = urlsplit(src)
                params = parse_qs(split_url.query)
                if 'auth' in params:
                    break
        if 'auth' in params:
            img_src = site_json['resizer_url'] + split_url.path + '?auth=' + params['auth'][0] + '&width=' + str(width) + '&quality=80&smart=true'
        elif image_item.get('auth') and image_item['_id'] in image_item['url']:
            auth = list(image_item['auth'].values())[0]
            split_url = urlsplit(image_item['url'])
            paths = list(filter(None, split_url.path[1:].split('/')))
            img_src = site_json['resizer_url'] + site_json['resizer_path'] + paths[-1] + '?auth=' + auth + '&width=' + str(width) + '&quality=80&smart=true'
        else:
            logger.warning('fullSizeResizeUrl image without auth ' + image_item['_id'])
            img_src = image_item['url']
    elif image_item.get('auth'):
        auth = list(image_item['auth'].values())[0]
        img_src = site_json['resizer_url'] + site_json['resizer_path'] + quote_plus(image_item['url']) + '?auth=' + auth + '&width=' + str(width) + '&quality=80&smart=true'
    elif image_item.get('resized_obj'):
        images = []
        for key, val in image_item['resized_obj'].items():
            split_url = urlsplit(val['src'])
            params = parse_qs(split_url.query)
            if 'auth' in params:
                img_src = site_json['resizer_url'] + split_url.path + '?auth=' + params['auth'][0] + '&width=' + str(width) + '&quality=80&smart=true'
                break
            elif 'width' in params:
                image = {
                    "width": int(params['width'][0]),
                    "src": val['src']
                }
                images.append(image)
        if not img_src and images:
            image = utils.closest_dict(images, 'width', width)
            img_src = image['src']
    elif image_item.get('renditions'):
        images = []
        for key, val in image_item['renditions']['original'].items():
            image = {
                "width": int(key[:-1]),
                "url": val
            }
            images.append(image)
        image = utils.closest_dict(images, 'width', width)
        img_src = image['url']
    if not img_src:
        img_src = image_item['url']
    return img_src


def process_content_element(element, url, site_json, save_debug):
    # print(element)
    split_url = urlsplit(url)
    element_html = ''
    if element['type'] == 'text' or element['type'] == 'paragraph':
        # Filter out ad content
        if not re.search(r'adsrv|amzn\.to|fanatics\.com|joinsubtext\.com|lids\.com|nflshop\.com|^<b>\[DOWNLOAD:\s*</b>|^<b>\[SIGN UP:\s*</b>|^<b>Read:\s*</b>|/live-breaking/.*STREAM|/our-apps/.*instructions', element['content'], flags=re.I):
            content = re.sub(r'href="/', 'href="https://{}/'.format(split_url.netloc), element['content'])
            element_html += '<p>' + content + '</p>'

    elif element['type'] == 'raw_html':
        # Filter out ad content
        if element['content'].startswith('<span data-dsid-content='):
            raw_soup = BeautifulSoup(element['content'].strip(), 'html.parser')
            for el in raw_soup.find_all('a'):
                link = utils.get_redirect_url(el['href'])
                el.attrs = {}
                el['href'] = link
            element_html = str(raw_soup)
        elif element['content'].strip() and not re.search(r'adiWidgetId|adsrv|amzn\.to|EMAIL/TWITTER|fanatics\.com|joinsubtext\.com|lids\.com|link\.[^\.]+\.com/s/Newsletter|mass-live-fanduel|nflshop\.com|\boffer\b|subscriptionPanel|tarot\.com|mailto:newsdesk\@nzme', element['content'], flags=re.I):
            if element['content'].startswith('%3C'):
                raw_soup = BeautifulSoup(unquote_plus(element['content']).strip(), 'html.parser')
            else:
                raw_soup = BeautifulSoup(element['content'].strip(), 'html.parser')
            #print(raw_soup.contents[0].name)
            if raw_soup.iframe:
                if raw_soup.iframe.get('data-fallback-image-url'):
                    element_html += utils.add_image(raw_soup.iframe['data-fallback-image-url'], link=raw_soup.iframe['src'])
                elif raw_soup.iframe.get('data-url'):
                    data_content = utils.get_content(raw_soup.iframe['data-url'], {}, save_debug)
                    if data_content and data_content.get('_image'):
                        #print(data_content['url'])
                        caption = '<a href="{}/content?read&url={}">{}</a>'.format(config.server, quote_plus(data_content['url']), data_content['title'])
                        element_html += utils.add_image(data_content['_image'], caption, link=data_content['url'])
                    else:
                        element_html += '<blockquote><b>Embedded content from <a href="{0}</a>{0}</b></blockquote>'.format(raw_soup.iframe['data-url'])
                else:
                    element_html += utils.add_embed(raw_soup.iframe['src'])
            elif raw_soup.blockquote and raw_soup.blockquote.get('class'):
                if 'tiktok-embed' in raw_soup.blockquote['class']:
                    element_html += utils.add_embed(raw_soup.blockquote['cite'])
                elif 'instagram-media' in raw_soup.blockquote['class']:
                    element_html += utils.add_embed(raw_soup.blockquote['data-instgrm-permalink'])
            elif raw_soup.script and raw_soup.script.get('src'):
                if 'sendtonews.com' in raw_soup.script['src']:
                    element_html += utils.add_embed(raw_soup.script['src'])
            elif raw_soup.find('aside', class_='refer'):
                it = raw_soup.find('aside', class_='refer')
                element_html += utils.add_blockquote(it.decode_contents())
            elif raw_soup.contents[0].name == 'img':
                element_html += utils.add_image(raw_soup.img['src'])
            elif raw_soup.contents[0].name == 'table':
                element_html += element['content']
            elif raw_soup.contents[0].name == 'div' and 'inline-photo' in raw_soup.contents[0].get('class'):
                element_html += utils.add_image(raw_soup.img['src'])
            elif raw_soup.contents[0].name == 'div' and raw_soup.contents[0].get('data-fallback-image-url'):
                element_html += utils.add_image(raw_soup.contents[0]['data-fallback-image-url'])
            elif raw_soup.contents[0].name == 'hl2':
                element_html += element['content'].replace('hl2', 'h2')
            elif raw_soup.contents[0].name == 'ad' or raw_soup.contents[0].name == 'quizbespoke' or raw_soup.contents[0].name == 'style':
                # can usually skip these
                pass
            elif element.get('subtype') and element['subtype'] == 'subs_form':
                pass
            else:
                #element_html += '<p>{}</p>'.format(element['content'])
                logger.warning('unhandled raw_html ')
                print(element['content'])

    elif element['type'] == 'custom_embed':
        if element['subtype'] == 'custom-image':
            captions = []
            if element['embed']['config'].get('image_caption'):
                captions.append(element['embed']['config']['image_caption'])
            if element['embed']['config'].get('image_credit'):
                captions.append(element['embed']['config']['image_credit'])
            img_src = resize_image({"url": element['embed']['config']['image_src']}, site_json)
            element_html += utils.add_image(img_src, ' | '.join(captions))
        elif element['subtype'] == 'custom-audio':
            episode = element['embed']['config']['episode']
            poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(episode['image']))
            element_html += '<div><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><h4>{}</h4><div style="clear:left;"></div><blockquote><small>{}</small></blockquote></div>'.format(
                episode['audio'], poster, episode['title'], episode['summary'])
        elif element['subtype'] == 'audio':
            element_html += utils.add_embed(element['embed']['url'])
        elif element['subtype'] == 'inline_audio':
            # Might be WaPo specific
            # https://www.washingtonpost.com/technology/2023/07/10/printer-home-hacks-tips/
            audio_html = ''
            if 'washpost' in element['embed']['url']:
                audio_url = '{}/findBySlug/{}'.format(site_json['audio_api'], element['embed']['config']['slug'])
                audio_json = utils.get_url_json(audio_url)
                if audio_json:
                    poster = '{}/image?url={}&width=128&overlay=audio'.format(config.server, quote_plus(audio_json['images']['coverImage']['url']))
                    audio_html += '<table><tr><td><a href="{}"><img src="{}" /></a></td>'.format(audio_json['audio']['url'], poster)
                    audio_html += '<td style="vertical-align:top;"><div style="font-size:1.1em; font-weight:bold;"><a href="{}://{}{}">{}</a></div>'.format(split_url.scheme, split_url.netloc, audio_json['canonicalUrl'], audio_json['title'])
                    audio_html += '<div>by <a href="{}://{}/{}">{}</a></div>'.format(split_url.scheme, split_url.netloc, audio_json['seriesMeta']['seriesSlug'], audio_json['seriesMeta']['seriesName'])
                    dt = datetime.fromtimestamp(audio_json['publicationDate']/1000).replace(tzinfo=timezone.utc)
                    duration = []
                    s = audio_json['duration']
                    if s > 3600:
                        h = s / 3600
                        duration.append('{} hr'.format(math.floor(h)))
                        m = (s % 3600) / 60
                        duration.append('{} min'.format(math.ceil(m)))
                    else:
                        m = s / 60
                        duration.append('{} min'.format(math.ceil(m)))
                    audio_html += '<div style="font-size:0.9em;">{} &bull; {}</div>'.format(utils.format_display_date(dt, False), ', '.join(duration))
                    audio_html += '<div style="font-size:0.8em;">{}</div></td></tr></table>'.format(audio_json['shortDescription'])
            if audio_html:
                element_html += audio_html
            else:
                logger.warning('unhandled custom_embed inline_audio')
        elif element['subtype'] == 'video' and element['embed']['config'].get('contentUrl') and 'jwplayer' in element['embed']['config']['contentUrl']:
            element_html += utils.add_embed(element['embed']['config']['contentUrl'])
        elif element['subtype'] == 'videoplayer' and element['embed']['config'].get('videoCode'):
            if element['embed']['config']['videoCode'].startswith('http'):
                element_html += utils.add_embed(element['embed']['config']['videoCode'])
            elif element['embed']['config']['videoCode'].startswith('<script'):
                m = re.search(r'src="([^"]+)', element['embed']['config']['videoCode'])
                if m:
                    element_html += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled custom_embed videoplayer videoCode')
        elif element['subtype'] == 'jwplayer':
            video_url = 'https://cdn.jwplayer.com/players/{}-{}.html'.format(element['embed']['config']['videoId'], element['embed']['config']['playerId'])
            element_html += utils.add_embed(video_url)
        elif element['subtype'] == 'video_dm':
            element_html += utils.add_embed(element['embed']['config']['url'])
        elif element['subtype'] == 'oovvuu-video':
            video_json = utils.get_url_json('https://playback.oovvuu.media/embed/d3d3LnRoZXN0YXIuY29t/{}'.format(element['embed']['config']['embedId']))
            if video_json:
                utils.write_file(video_json, './debug/video.json')
                # "data-key": "BCpkADawqM02UpPUkzc8xH5Bd3-cUq0R9yd9J44SrfoXNajUlAnL6l--3PUnKFaoBa2cWhTYVjtnL20g-dK2t5i2TPJSnXqImIvT_aNrKa4oZN4_ZI3PVVR4S1A-hxd2XgABF1ZBQI-7bQvzHnInuey3CFEvla5Awnx-tf5_iq_IS9XXNLt1w00d3PLm8cnKcX4Qmi2yRSQZimMQyGUhbXywrF6YTC5WaBPG5jqpO-_Ht4LrOZoVlKLkPRhqGh1Pq0Bmn4ucWl1J_hHRVIPBY9Pwd1b7IuenAaGcCg",
                if element['embed']['config'].get('thumbnailImageUrl'):
                    poster = utils.clean_url(element['embed']['config']['thumbnailImageUrl'])
                else:
                    poster = utils.clean_url(video_json['videos'][0]['video']['thumbnail']) + '?ixlib=js-2.3.2&w=1080&fit=crop&crop=entropy'
                video_args = {
                    "embed": True,
                    "data-account": video_json['videos'][0]['brightcoveAccountId'],
                    "data-video-id": video_json['videos'][0]['brightcoveVideoId'],
                    "poster": poster,
                    "title": 'Watch: ' + video_json['videos'][0]['video']['title']
                }
                element_html += utils.add_embed(video_json['playerScript'], video_args)
            else:
                logger.warning('unhandled oovvuu-video custom-embed')
        elif element['subtype'] == 'nzh_video':
            video_url = site_json['api_url'] + 'full-content-by-id?query=%7B%22id%22%3A%22{}%22%2C%22site%22%3A%22{}%22%7D&d={}&mxId=00000000&_website={}'.format(element['embed']['id'], element['embed']['config']['website'], site_json['deployment'], element['embed']['config']['website'])
            video_json = utils.get_url_json(video_url)
            if video_json:
                element_html += get_content_html(video_json, url, {"embed": True}, site_json, save_debug)
        elif element['subtype'] == 'Video Playlist':
            # https://www.atlantanewsfirst.com/2024/01/15/read-fulton-county-da-fani-willis-improper-relationship-charges/
            video_pls = utils.get_url_json('https://gray-config-prod.api.arc-cdn.net/video/v1/ans/playlists/findByPlaylist?name=' + quote_plus(element['embed']['id']))
            if video_pls:
                video = video_pls['playlistItems'][0]
                streams_mp4 = []
                streams_ts = []
                for stream in video['streams']:
                    if stream.get('stream_type'):
                        if stream['stream_type'] == 'mp4':
                            streams_mp4.append(stream)
                        elif stream['stream_type'] == 'ts':
                            streams_ts.append(stream)
                    else:
                        if re.search(r'\.mp4', stream['url']):
                            streams_mp4.append(stream)
                        elif re.search(r'\.m3u8', stream['url']):
                            streams_ts.append(stream)
                stream = None
                if streams_ts:
                    if streams_ts[0].get('height'):
                        stream = utils.closest_dict(streams_ts, 'height', 720)
                    else:
                        stream = streams_ts[0]
                    stream_type = 'application/x-mpegURL'
                elif streams_mp4:
                    if streams_mp4[0].get('height'):
                        stream = utils.closest_dict(streams_mp4, 'height', 720)
                    else:
                        stream = streams_mp4[0]
                    stream_type = 'video/mp4'
                if stream:
                    poster = video['promo_image']['url']
                    element_html += utils.add_video(stream['url'], stream_type, poster, video['headlines']['basic'])
        elif element['subtype'] == 'syncbak-graph-livestream':
            engine_js = utils.get_url_html('https://{}/pf/dist/engine/react.js?d=901&mxId=00000000'.format(urlsplit(site_json['api_url']).netloc, site_json['deployment']))
            if engine_js:
                for site in re.findall(r'\{e.exports=JSON.parse\(\'(.*?)\'\)\}', engine_js):
                    if re.search(r'"siteShorthand":"{}"'.format(element['embed']['config']['website']), site):
                        break
                m = re.search(r'"appName":"([^"]+)', site)
                if m:
                    def device_id(e=21):
                        t = ""
                        r = e
                        characters = "useandom-26T198340PX75pxJACKVERYMINDBUSHWOLF_GQZbfghjklqvwyzrict"
                        while r > 0:
                            t += characters[int(64 * random.random())]
                            r -= 1
                        return t
                    device_data = {
                        "appName": m.group(1),
                        "appPlatform": "web",
                        "bundleId": "dev",
                        "deviceId": device_id(50),
                        "deviceType": 8
                    }
                    m = re.search(r'{}_ZEAM_TOKEN:"([^"]+)'.format(element['embed']['config']['website']), engine_js, flags=re.I)
                    if m:
                        headers = {
                            "accept": "application/json",
                            "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
                            "api-device-data": base64.b64encode(json.dumps(device_data, separators=(',', ':')).encode()).decode(),
                            "api-token": m.group(1),
                            "content-type": "application/json",
                            "priority": "u=1, i",
                            "sec-ch-ua": "\"Microsoft Edge\";v=\"135\", \"Not-A.Brand\";v=\"8\", \"Chromium\";v=\"135\"",
                            "sec-ch-ua-mobile": "?0",
                            "sec-ch-ua-platform": "\"Windows\"",
                            "sec-fetch-dest": "empty",
                            "sec-fetch-mode": "cors",
                            "sec-fetch-site": "cross-site"
                        }
                        data = {
                            "query": " query GrayWebAppsLiveChannelData($expirationSeconds: Int, $liveChannelId: ID!) { liveChannel (id: $liveChannelId, orEquivalent: true){ id title description callsign listImages { type url size } posterImages { type url size } isNew type status onNow { id title description episodeTitle tvRating startTime endTime duration isLooped isOffAir airDate} onNext { id title description episodeTitle tvRating startTime endTime duration isLooped isOffAir airDate} isNielsenEnabled isClosedCaptionEnabled location networkAffiliation taxonomy { facet terms } streamUrl(expiresIn: $expirationSeconds) } liveChannels { id title description callsign listImages { type url size } posterImages { type url size } isNew type status onNow { id title description episodeTitle tvRating startTime endTime duration isLooped isOffAir airDate} onNext { id title description episodeTitle tvRating startTime endTime duration isLooped isOffAir airDate} isNielsenEnabled isClosedCaptionEnabled location networkAffiliation taxonomy { facet terms } } }",
                            "variables": {
                                "expirationSeconds": 300,
                                "liveChannelId": element['embed']['config']['channelId']
                            }
                        }
                        video_json = utils.post_url('https://graphql-api.aws.syncbak.com/graphql', json_data=data, headers=headers)
                        if video_json:
                            element_html += utils.add_video(video_json['data']['liveChannel']['streamUrl'], 'application/x-mpegURL', video_json['data']['posterImages'][0]['url'], 'Live stream: ' + video_json['data']['title'])
        elif element['subtype'] == 'datawrapper':
            element_html += utils.add_embed(element['embed']['url'])
        elif element['subtype'] == 'flourish_visualisation':
            embed_url = 'https://flo.uri.sh/visualisation/{}/embed?auto=1'.format(element['embed']['config']['visualizationNumber'])
            element_html += utils.add_image('{}/screenshot?url={}&locator=main&width=1200&height=800'.format(config.server, quote_plus(embed_url)), '<a href="{}">View Flourish Visualization</a>'.format(embed_url))
        elif element['subtype'] == 'stars_notation':
            if element['embed']['config'].get('notationTitle'):
                element_html += '<div style="font-size:1.2em; font-weight:bold; text-align:center;">' + element['embed']['config']['notationTitle'] + '</div>'
            element_html += utils.add_stars(float(element['embed']['config']['notationValue']))
            if element['embed']['config'].get('notationDescription'):
                element_html += '<div style="font-size:0.8em; width:20em; margin:auto;">' + BeautifulSoup(element['embed']['config']['notationDescription'].replace('&nbsp;', ' '), 'html.parser').get_text() + '</div>'
        elif element['subtype'] == 'tabseparator':
            element_html += '<div>&nbsp;</div><hr/><div>&nbsp;<h2>{}</h2></div>'.format(unquote_plus(element['embed']['config']['tabTitle']))
            if element['embed']['config']['contentSource'] == 'dynamic':
                opts = json.loads(unquote_plus(element['embed']['config']['opts']))
                embed_url = '{}{}?query={}&d={}&_website={}'.format(site_json['api_url'], opts['contentAPI'], element['embed']['config']['opts'], site_json['deployment'], site_json['arc_site'])
                embed_json = utils.get_url_json(embed_url)
                if embed_json:
                    #utils.write_file(embed_json, './debug/embed.json')
                    for el in embed_json['content_elements']:
                        if el['type'] == 'story':
                            embed_item = get_item(el, url, {'embed': True}, site_json, save_debug)
                            if embed_item:
                                element_html += embed_item['content_html'] + '<div>&nbsp;</div>'
                        else:
                            content_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, el['canonical_url'])
                            content_json = utils.get_url_json('{}content-api?query=%7B%22_id%22%3A%22{}%22%7D&d={}&_website={}'.format(site_json['api_url'], el['_id'], site_json['deployment'], site_json['arc_site']))
                            if content_json:
                                #utils.write_file(content_json, './debug/content.json')
                                element_html += process_content_element(content_json, content_url, site_json, save_debug)
        elif element['subtype'] == 'arena-api-inline':
            arena_url = '{}arena-cache-api?query=%7B%22embedSlug%22%3A%22{}%22%2C%22provider%22%3A%22arena-api-inline%22%7D&d={}&_website={}'.format(site_json['api_url'], element['embed']['config']['embedId'], site_json['deployment'], site_json['arc_site'])
            arena_json = utils.get_url_json(arena_url)
            if arena_json:
                # utils.write_file(arena_json, './debug/arena.json')
                n = len(arena_json['posts']) - 1
                for i, post in enumerate(arena_json['posts']):
                    dt = datetime.fromtimestamp(post['createdAt']/1000).replace(tzinfo=timezone.utc)
                    element_html += '<div>Update: {}</div>'.format(utils.format_display_date(dt))
                    if post.get('sender'):
                        element_html += '<div>By {}</div>'.format(post['sender']['displayName'])
                    if post['message'].get('title'):
                        element_html += '<h3>{}</h3>'.format(post['message']['title'])
                    if post['message'].get('media'):
                        if post['message']['media']['providerName'] == 'Twitter' or post['message']['media']['providerName'] == 'YouTube':
                            element_html += utils.add_embed(post['message']['media']['url'])
                        else:
                            logger.warning('unhandled arena media provider ' + post['message']['media']['providerName'])
                    if post['message'].get('text'):
                        post_soup = BeautifulSoup(post['message']['text'], 'html.parser')
                        for img in post_soup.find_all('img'):
                            caption = ''
                            fig = img.find_parent('figure')
                            if fig:
                                el = fig.find('figcaption')
                                if el:
                                    caption = el.decode_contents()
                            else:
                                fig = img
                            new_html = utils.add_image(img['src'], caption)
                            new_el = BeautifulSoup(new_html, 'html.parser')
                            p = fig.find_parent('p')
                            if p:
                                p.insert_before(new_el)
                            else:
                                fig.insert_before(new_el)
                            fig.decompose()
                        element_html += str(post_soup)
                    if i < n:
                        element_html += '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
        elif element['subtype'] == 'inset':
            embed_html = ''
            if element['embed']['config'].get('headline'):
                embed_html += '<div style="font-size:1.1em; font-weight:bold">{}</div>'.format(element['embed']['config']['headline'])
            embed_html += element['embed']['config']['content']
            element_html += utils.add_blockquote(embed_html)
        elif element['subtype'] == 'section-info':
            # https://www.dlnews.com/articles/markets/gbtc-could-see-billions-leave-its-bitcoin-etf-says-jpmorgan/
            element_html += '<ul>'
            for it in element['embed']['config']['text'].split('\n'):
                if it.strip():
                    element_html += '<li>' + it + '</li>'
            element_html += '</ul>'
        elif re.search(r'iframe', element['subtype'], flags=re.I):
            embed_html = base64.b64decode(element['embed']['config']['base64HTML']).decode('utf-8')
            m = re.search(r'src="([^"]+)"', embed_html)
            if m:
                element_html += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled custom_embed iframe')
        elif element['subtype'] == 'Axis Video' and element['embed']['config']['brand'] == 'BNN':
            # https://www.bnnbloomberg.ca/business/company-news/2024/11/12/bang-up-quarter-across-the-board-experts-react-to-shopifys-q3-earnings-beat/
            # TODO: bnnbloomberg.ca specific?
            video_url = 'https://capi.9c9media.com/destinations/bnn_web/platforms/desktop/contents/{}?%24lang=en&%24include=%5BDesc%2CType%2CMedia%2CImages%2CContentPackages%2CAuthentication%2CSeason%2CChannelAffiliate%2COwner%2CRevShare%2CAdTarget%2CKeywords%2CAdRights%2CTags%5D'.format(element['embed']['config']['id'])
            video_json = utils.get_url_json(video_url)
            if video_json:
                video_url = 'https://capi.9c9media.com/destinations/bnn_web/platforms/desktop/bond/contents/{}/contentPackages/{}/manifest.pmpd?action=reference&ssl=true&filter=13'.format(video_json['Id'], video_json['ContentPackages'][0]['Id'])
                video = utils.get_url_html(video_url)
                if video:
                    element_html += utils.add_video(video, 'application/dash+xml', element['embed']['config']['thumbnailUrl'], element['embed']['config']['title'])
        elif element['subtype'] == 'Stock Widgets':
            # TODO: bnnbloomberg.ca specific?
            # https://www.bnnbloomberg.ca/business/company-news/2024/11/12/bang-up-quarter-across-the-board-experts-react-to-shopifys-q3-earnings-beat/
            stock_id = next((it for it in element['embed']['config']['selectedWidget']['props'] if it['name'] == 'custom-id'), None)
            if stock_id:
                stock_url = 'https://bnn.stats.bellmedia.ca/bnn/api/stock/infos?brand=bnn&lang=en&symbol=' + stock_id['value']
                stock_json = utils.get_url_json(stock_url)
                if stock_json:
                    if stock_json[0]['percentChange'].startswith('-'):
                        color = 'red'
                    else:
                        color = 'green'
                    element_html += '<h3 style="text-align:center;">{} (<a href="https://www.bnnbloomberg.ca/stock/{}/">{}</a>): ${} <span style="color:{};">{} ({}%)</span></h3>'.format(stock_json[0]['name'], stock_json[0]['symbol'], stock_json[0]['symbol'], stock_json[0]['price'], color, stock_json[0]['netChange'], stock_json[0]['percentChange'])
        elif element['subtype'] == 'magnet' or element['subtype'] == 'newsletter_signup' or element['subtype'] == 'newslettersignup-composer' or element['subtype'] == 'now-read' or element['subtype'] == 'read_also' or element['subtype'] == 'related_story' or element['subtype'] == 'SubjectTag' or element['subtype'] == 'Alternate Headlines':
            pass
        else:
            logger.warning('unhandled custom_embed ' + element['subtype'])

    elif element['type'] == 'divider':
        element_html += '<div>&nbsp;</div><hr/><div>&nbsp;</div>'

    elif element['type'] == 'correction':
        element_html += '<blockquote><b>{}</b><br>{}</blockquote>'.format(element['correction_type'].upper(),element['text'])

    elif element['type'] == 'quote':
        text = ''
        for el in element['content_elements']:
            text += process_content_element(el, url, site_json, save_debug)
        if element.get('citation'):
            cite = element['citation']['content']
        else:
            cite = ''
        if element.get('subtype'):
            if element['subtype'] == 'pullquote' or (element['subtype'] == 'blockquote' and cite):
                element_html += utils.add_pullquote(text, cite)
            elif element['subtype'] == 'blockquote':
                element_html += utils.add_blockquote(text)
            else:
                logger.warning('unhandled quote item type {}'.format(element['subtype']))
        else:
            element_html += utils.add_pullquote(text, cite)

    elif element['type'] == 'header':
        element_html += '<h{0}>{1}</h{0}>'.format(element['level'], element['content'])

    elif element['type'] == 'oembed_response':
        if element.get('subtype'):
            if element['subtype'] == 'instagram' or element['subtype'] == 'spotify' or element['subtype'] == 'twitter' or element['subtype'] == 'youtube' or element['subtype'] == 'facebook-post':
                if element.get('referent'):
                    element_html += utils.add_embed(element['referent']['id'])
                elif element.get('raw_oembed'):
                    element_html += utils.add_embed(element['raw_oembed']['_id'])
                else:
                    logger.warning('unhandled oembed_response subtype ' + element['subtype'])    
            else:
                logger.warning('unhandled oembed_response subtype ' + element['subtype'])
        elif element['raw_oembed'].get('_id') and element['raw_oembed']['_id'].startswith('http'):
            element_html += utils.add_embed(element['raw_oembed']['_id'])
        elif element['raw_oembed'].get('url') and element['raw_oembed']['url'].startswith('http'):
            element_html += utils.add_embed(element['raw_oembed']['url'])
        else:
            logger.warning('unhandled oembed_response url')

    elif element['type'] == 'list':
        if element['list_type'] == 'unordered':
            element_html += '<ul>'
        else:
            element_html += '<ol>'
        for it in element['items']:
            if it['type'] == 'text':
                element_html += '<li>{}</li>'.format(it['content'])
            elif it['type'] == 'list':
                element_html += '{}'.format(process_content_element(it, url, site_json, save_debug))
            else:
                logger.warning('unhandled list item type {}'.format(element['type']))
        if element['list_type'] == 'unordered':
            element_html += '</ul>'
        else:
            element_html += '</ol>'

    elif element['type'] == 'table':
        element_html += '<table style="width:100%; border-collapse:collapse;">'
        if element.get('header'):
            element_html += '<tr>'
            for it in element['header']:
                if isinstance(it, str):
                    element_html += '<th style="text-align:left;">{}</th>'.format(it)
                elif isinstance(it, dict) and it.get('type') and it['type'] == 'text':
                    element_html += '<th style="text-align:left;">{}</th>'.format(it['content'])
                else:
                    logger.warning('unhandled table header item type {}'.format(element['type']))
            element_html += '</tr>'
        for row in element['rows']:
            element_html += '<tr>'
            for it in row:
                if isinstance(it, str):
                    element_html += '<td>{}</td>'.format(it)
                elif isinstance(it, dict) and it.get('type') and it['type'] == 'text':
                    element_html += '<td>{}</td>'.format(it['content'])
                else:
                    logger.warning('unhandled table row item type {}'.format(element['type']))
            element_html += '</tr>'
        element_html += '</table>'

    elif element['type'] == 'image':
        if element['image_type'] == 'graphic' and re.search(r'Roku|Watch Anywhere', element['alt_text']):
            # Skip
            return ''
        img_src = resize_image(element, site_json)
        captions = []
        if element.get('credits_caption_display'):
            captions.append(element['credits_caption_display'])
        else:
            if element.get('caption') and element['caption'] != '-':
                captions.append(
                    re.sub(r'^<p>|</p>$', '', element['caption'])
                )
            if element.get('credits'):
                if element['credits'].get('by') and element['credits']['by'][0].get('byline'):
                    if element['credits']['by'][0]['byline'] == 'Fanatics':
                        # Skip ad
                        img_src = ''
                    else:
                        captions.append(element['credits']['by'][0]['byline'])
                elif element['credits'].get('affiliation'):
                    captions.append(
                        re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in element['credits']['affiliation']]))
                    )
        caption = ' | '.join(captions)
        #if element.get('subtitle') and element['subtitle'].strip():
        #    caption = '<strong>{}.</strong> '.format(element['subtitle'].strip()) + caption
        if img_src:
            element_html += utils.add_image(img_src, caption)

    elif element['type'] == 'gallery':
        img_src = resize_image(element['content_elements'][0], site_json)
        link = '{}://{}'.format(split_url.scheme, split_url.netloc)
        if element.get('canonical_url'):
            link += element['canonical_url']
        elif element.get('slug'):
            link += element['slug']
        caption = '<strong>Gallery:</strong> <a href="{}">{}</a>'.format(link, element['headlines']['basic'])
        link = '{}/content?read&url={}'.format(config.server, quote_plus(link))
        if img_src:
            element_html += utils.add_image(img_src, caption, link=link, overlay=config.gallery_button_overlay)

    elif element['type'] == 'graphic':
        if element['graphic_type'] == 'image':
            captions = []
            if element.get('title'):
                captions.append(element['title'].capitalize())
            if element.get('byline'):
                captions.append(element['byline'])
            element_html += utils.add_image(element['url'], ' | '.join(captions))
        elif element.get('preview_image'):
            captions = []
            if element.get('title'):
                captions.append(element['title'])
            if element.get('byline'):
                captions.append(element['byline'])
            element_html += utils.add_image(element['preview_image']['url'], ' | '.join(captions), link=element['url'])
        else:
            logger.warning('unhandled graphic type {}'.format(element['graphic_type']))

    elif element['type'] == 'video':
        if 'washingtonpost.com' in split_url.netloc:
            api_url = 'https://video-api.washingtonpost.com/api/v1/ansvideos/findByUuid?uuid=' + element['_id']
            api_json = utils.get_url_json(api_url)
            if api_json:
                video_json = api_json[0]
        elif not element.get('streams'):
            api_url = '{}video-by-id?query=%7B%22id%22%3A%22{}%22%7D&d={}&_website={}'.format(site_json['api_url'], element['_id'], site_json['deployment'], site_json['arc_site'])
            api_json = utils.get_url_json(api_url)
            if api_json:
                video_json = api_json
        else:
            video_json = element
        #utils.write_file(video_json, './debug/video.json')
        streams_mp4 = []
        streams_ts = []
        for stream in video_json['streams']:
            if stream.get('stream_type'):
                if stream['stream_type'] == 'mp4':
                    streams_mp4.append(stream)
                elif stream['stream_type'] == 'ts':
                    streams_ts.append(stream)
            else:
                if re.search(r'\.mp4', stream['url']):
                    streams_mp4.append(stream)
                elif re.search(r'\.m3u8', stream['url']):
                    streams_ts.append(stream)
        stream = None
        if streams_ts:
            if streams_ts[0].get('height'):
                stream = utils.closest_dict(streams_ts, 'height', 720)
            else:
                stream = streams_ts[0]
            stream_type = 'application/x-mpegURL'
        elif streams_mp4:
            if streams_mp4[0].get('height'):
                stream = utils.closest_dict(streams_mp4, 'height', 720)
            else:
                stream = streams_mp4[0]
            stream_type = 'video/mp4'
        if stream:
            if element.get('imageResizerUrls'):
                poster = utils.closest_dict(element['imageResizerUrls'], 'width', 1000)
            elif element.get('promo_image'):
                poster = resize_image(element['promo_image'], site_json)
            else:
                poster = ''
            element_html += utils.add_video(stream['url'], stream_type, poster, element['headlines']['basic'])
        else:
            logger.warning('unhandled video streams')

    elif element['type'] == 'social_media' and element['sub_type'] == 'twitter':
        links = BeautifulSoup(element['html'], 'html.parser').find_all('a')
        element_html += utils.add_embed(links[-1]['href'])

    elif element['type'] == 'reference':
        # print(element)
        if element.get('referent') and element['referent'].get('id'):
            if element['referent']['type'] == 'image':
                captions = []
                if element['referent']['referent_properties'].get('caption'):
                    captions.append(element['referent']['referent_properties']['caption'])
                if element['referent']['referent_properties'].get('vanity_credits') and element['referent']['referent_properties']['vanity_credits'].get('by'):
                    for it in element['referent']['referent_properties']['vanity_credits']['by']:
                        captions.append(it['name'])
                img_src = site_json['referent_image_path'] + element['referent']['id']
                if utils.url_exists(img_src + '.jpg'):
                    img_src += '.jpg'
                else:
                    img_src += '.png'
                if element['referent'].get('auth'):
                    img_src += '?auth=' + element['referent']['auth']['1']
                element_html += utils.add_image(img_src, ' | '.join(captions))
            elif element['referent']['id'].startswith('http'):
                element_html += utils.add_embed(element['referent']['id'])
            else:
                logger.warning('unhandled referent id ' + element['referent']['id'])
        else:
            logger.warning('unhandled reference element')

    elif element['type'] == 'story':
        # This may be Wapo specific
        if site_json.get('add_story'):
            headline = element['headlines']['basic']
            if '<' in headline:
                # Couple of cases of unclosed html tags in the headline, just use the text
                headline = BeautifulSoup(headline, 'html.parser').get_text()
            element_html += '<div>&nbsp;</div><hr><h2>{}</h2>'.format(headline)
            authors = []
            for author in element['credits']['by']:
                if author.get('name'):
                    authors.append(author['name'])
            tz_est = pytz.timezone('US/Eastern')
            dt = datetime.fromisoformat(element['display_date'].replace('Z', '+00:00')).astimezone(tz_est)
            date = utils.format_display_date(dt)
            #date = '{}. {}, {} {}'.format(dt.strftime('%b'), dt.day, dt.year, dt.strftime('%I:%M %p').lstrip('0'))
            if authors:
                byline = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
                element_html += '<p>by {} (updated {})</p>'.format(byline, date)
            else:
                element_html += '<p>updated {}</p>'.format(date)
            element_html += get_content_html(element, url, {}, site_json, save_debug)
            element_html += '<div>&nbsp;</div><hr><div>&nbsp;</div>'.format(headline)

    elif element['type'] == 'link_list':
        if 'subtype' not in element and element['items'][0]['type'] == 'interstitial_link':
            if element.get('title'):
                element_html += '<h3>{}</h3>'.format(element['title'])
            element_html += '<ul>'
            for it in element['items']:
                element_html += '<li><a href="{}" target="_blank">{}</a></li>'.format(it['url'], it['content'])
            element_html += '</ul>'
        elif element['subtype'] == 'key-moments' :
            if element.get('title'):
                element_html += '<h3>{}</h3>'.format(element['title'])
            element_html += '<ul>'
            for it in element['items']:
                element_html += '<li>{}</li>'.format(it['content'])
            element_html += '</ul>'
        elif element['subtype'] == 'button/btn_btn-primary/1':
            # https://www.atlantanewsfirst.com/2024/01/15/read-fulton-county-da-fani-willis-improper-relationship-charges/
            if element.get('title'):
                element_html += '<h3>{}</h3>'.format(element['title'])
            for it in element['items']:
                element_html += utils.add_button(it['url'], it['content'])
        elif element['subtype'] == 'link-list' or element['subtype'] == 'splash-story-bullet':
            pass
        else:
            logger.warning('unhandled link_list subtype ' + element['subtype'])

    elif element['type'] == 'interstitial_link':
        pass

    else:
        logger.warning('unhandled element type {}'.format(element['type']))
        #print(element)
    return element_html


def get_content_html(content, url, args, site_json, save_debug):
    split_url = urlsplit(url)
    content_html = ''
    if content['type'] == 'video' and content.get('brightcoveId'):
        engine_js = utils.get_url_html('https://{}/pf/dist/engine/react.js?d=901&mxId=00000000'.format(urlsplit(site_json['api_url']).netloc, site_json['deployment']))
        if engine_js:
            video_url = 'https://players.brightcove.net/'
            m = re.search(r'BC_ACCOUNT_ID:"([^"]+)"', engine_js)
            if m:
                video_url += m.group(1) + '/'
                m = re.search(r'BC_PLAYER_ID:"([^"]+)"', engine_js)
                if m:
                    video_url += m.group(1) + '_default/index.html?videoId=' + content['brightcoveId']
                    content_html += utils.add_embed(video_url)
                    if 'embed' not in args and content.get('description'):
                        content_html += '<p>' + content['description'] + '</p>'
                    return content_html
    elif content['type'] == 'video':
        streams_mp4 = []
        streams_ts = []
        for stream in content['streams']:
            if stream['stream_type'] == 'mp4':
                streams_mp4.append(stream)
            elif stream['stream_type'] == 'ts':
                streams_ts.append(stream)
        stream = None
        if streams_ts:
            stream = utils.closest_dict(streams_ts, 'height', 720)
            stream_type = 'application/x-mpegURL'
        elif streams_mp4:
            stream = utils.closest_dict(streams_mp4, 'height', 720)
            stream_type = 'video/mp4'
        if stream:
            if content.get('imageResizerUrls'):
                poster = utils.closest_dict(content['imageResizerUrls'], 'width', 1000)
            elif content.get('promo_image'):
                poster = resize_image(content['promo_image'], site_json)
            else:
                poster = ''
            if content.get('description'):
                caption = content['description']['basic']
            else:
                caption = ''
            content_html += utils.add_video(stream['url'], stream_type, poster, caption)
        else:
            logger.warning('no handled streams found for video content in ' + url)
        return content_html

    if content.get('subheadlines') and content['subheadlines'].get('basic'):
        content_html += '<p><em>' + content['subheadlines']['basic'] + '</em></p>'
    elif 'args' in site_json and 'add_subtitle' in site_json['args'] and content.get('description') and content['description'].get('basic'):
        content_html += '<p><em>' + content['description']['basic'] + '</em></p>'

    if content.get('summary'):
        content_html += '<ul>'
        for it in content['summary']:
            if it.get('link'):
                content_html += '<li><a href="{}">{}</a></li>'.format(it['link'], it['description'])
            else:
                content_html += '<li>{}</li>'.format(it['description'])
        content_html += '</ul>'

    lead_image = None
    if content.get('multimedia_main'):
        lead_image = content['multimedia_main']
    elif content.get('promo_items'):
        if content['promo_items'].get('video'):
            content_html += process_content_element(content['promo_items']['video'], url, site_json, save_debug)
        elif content['promo_items'].get('youtube'):
            content_html += utils.add_embed(content['promo_items']['youtube']['content'])
        elif content['promo_items'].get('lead_art') and content['promo_items']['lead_art'].get('subtype') != 'syncbak-graph-livestream':
            lead_image = content['promo_items']['lead_art']
        elif content['promo_items'].get('basic'):
            lead_image = content['promo_items']['basic']
        elif content['promo_items'].get('images'):
            lead_image = content['promo_items']['images'][0]
    elif content.get('customVideo'):
        content_html += process_content_element(content['customVideo'], url, site_json, save_debug)
    if lead_image and lead_image.get('_id') and content.get('content_elements'):
        for i in range(min(2, len(content['content_elements']))):
            if content['content_elements'][i]['_id'] == lead_image['_id']:
                lead_image = None
                break
        # if content['content_elements'][0]['_id'] == lead_image['_id']:
        #     lead_image = None
        # elif content['content_elements'][1]['_id'] == lead_image['_id']:
        #     lead_image = None
    if lead_image:
        if not lead_image.get('type'):
            lead_image['type'] = 'image'
        if not content.get('content_elements') or content['type'] == 'gallery' or (content['content_elements'][0]['type'] != 'image' and content['content_elements'][0]['type'] != 'video' and content['content_elements'][0].get('subtype') != 'youtube' and content['content_elements'][0].get('subtype') != 'video'):
            content_html += process_content_element(lead_image, url, site_json, save_debug)

    if content.get('content_elements'):
        skip_next = False
        for n, element in enumerate(content['content_elements']):
            if skip_next:
                skip_next = False
                continue
            if element['type'] == 'text' and (element['content'] == '<b>TRENDING STORIES:</b>' or element['content'] == '<b>RELATED COVERAGE:</b>') and content['content_elements'][n + 1]['type'] == 'list':
                skip_next = True
                continue
            content_html += process_content_element(element, url, site_json, save_debug)
    if content.get('elements'):
        for element in content['elements']:
            content_html += process_content_element(element, url, site_json, save_debug)

    if content.get('related_content') and content['related_content'].get('galleries'):
        for gallery in content['related_content']['galleries']:
            if gallery.get('canonical_url'):
                content_html += process_content_element(gallery, url, site_json, save_debug)
            else:
                content_html += '<h3>Photo Gallery</h3>'
                for element in gallery['content_elements']:
                    if lead_image and lead_image['id'] == element['id']:
                        continue
                    content_html += process_content_element(element, url, site_json, save_debug)

    # Reuters specific
    if content.get('related_content') and content['related_content'].get('videos'):
        content_html += '<h3>Related Videos</h3>'
        for video in content['related_content']['videos']:
            caption = '<b>{}</b> &mdash; {}'.format(video['title'], video['description'])
            if video['thumbnail'].get('renditions'):
                poster = video['thumbnail']['renditions']['original']['480w']
            elif video['thumbnail'].get('url'):
                poster = video['thumbnail']['url']
            else:
                logger.warning('unknown video thumbnail for id ' + video['id'])
                poster = ''
            if video['source'].get('mp4'):
                content_html += utils.add_video(video['source']['mp4'], 'video/mp4', poster, caption)
            elif video['source'].get('hls'):
                content_html += utils.add_video(video['source']['hls'], 'application/x-mpegURL', poster, caption)
            else:
                logger.warning('unhandled related content video in ' + url)

    if content.get('subtype'):
        if content['subtype'] == 'audio':
            audio_html = ''
            audio_url = '{}/{}'.format(site_json['audio_api'], content['fusion_additions']['audio']['id'])
            audio_json = utils.get_url_json(audio_url)
            if audio_json:
                poster = '{}/image?url={}&width=128&overlay=audio'.format(config.server, quote_plus(audio_json['images']['coverImage']['url']))
                audio_html += '<table><tr><td><a href="{}"><img src="{}" /></a></td>'.format(audio_json['audio']['url'], poster)
                audio_html += '<td style="vertical-align:top;"><div style="font-size:1.1em; font-weight:bold;"><a href="{}://{}{}">{}</a></div>'.format(split_url.scheme, split_url.netloc, audio_json['canonicalUrl'], audio_json['title'])
                audio_html += '<div>by <a href="{}://{}/{}">{}</a></div>'.format(split_url.scheme, split_url.netloc, audio_json['seriesMeta']['seriesSlug'], audio_json['seriesMeta']['seriesName'])
                dt = datetime.fromtimestamp(audio_json['publicationDate'] / 1000).replace(tzinfo=timezone.utc)
                duration = []
                s = audio_json['duration']
                if s > 3600:
                    h = s / 3600
                    duration.append('{} hr'.format(math.floor(h)))
                    m = (s % 3600) / 60
                    duration.append('{} min'.format(math.ceil(m)))
                else:
                    m = s / 60
                    duration.append('{} min'.format(math.ceil(m)))
                audio_html += '<div style="font-size:0.9em;">{} &bull; {}</div>'.format(utils.format_display_date(dt, False), ', '.join(duration))
                audio_html += '<div style="font-size:0.8em;">{}</div></td></tr></table>'.format(audio_json['shortDescription'])
            if audio_html:
                content_html += audio_html
            else:
                logger.warning('unhandled audio subtype in ' + url)

    if content.get('content_restrictions') and content['content_restrictions'].get('content_code') and content['content_restrictions']['content_code'] == 'hard-paywall':
        content_html += '<h2 style="text-align:center;"><a href="{}">This post is for paid subscribers</a></h2>'.format(url)

    content_html = re.sub(r'</figure><(figure|table)', r'</figure><div>&nbsp;</div><\1', content_html)
    return content_html


def get_item(content, url, args, site_json, save_debug):
    item = {}
    if content.get('_id'):
        item['id'] = content['_id']
    elif content.get('id'):
        item['id'] = content['id']
    else:
        item['id'] = url

    item['url'] = url
    if content.get('headlines'):
        item['title'] = content['headlines']['basic']
    elif content.get('title'):
        item['title'] = content['title']

    date = ''
    if content.get('first_publish_date'):
        date = content['first_publish_date']
    elif content.get('published_time'):
        date = content['published_time']
    elif content.get('display_date'):
        date = content['display_date']
    elif content.get('displayDate'):
        date = content['displayDate']
    if date:
        dt = datetime.fromisoformat(re.sub(r'(\.\d+)?Z$', '+00:00', date))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
    else:
        logger.warning('no publish date found in ' + item['url'])

    date = ''
    if content.get('last_updated_date'):
        date = content['last_updated_date']
    elif content.get('lastUpdatedDate'):
        date = content['lastUpdatedDate']
    elif content.get('updated_time'):
        date = content['updated_time']
    elif content.get('display_date'):
        date = content['display_date']
    if date:
        dt = datetime.fromisoformat(re.sub(r'(\.\d+)?Z$', '+00:00', date))
        item['date_modified'] = dt.isoformat()
    else:
        logger.warning('no updated date found in ' + item['url'])

    # Check age
    if 'age' in args:
        if not utils.check_age(item, args):
            return None

    authors = []
    if content.get('credits') and content['credits'].get('by'):
        for author in content['credits']['by']:
            if author['type'] == 'author':
                if author.get('name'):
                    authors.append(author['name'])
                elif author.get('org'):
                    authors.append(author['org'])
    if content.get('credits') and content['credits'].get('host_talent'):
        if content['credits'].get('host_talent'):
            for author in content['credits']['host_talent']:
                if author.get('name'):
                    authors.append(author['name'])
    if not authors:
        if content.get('authors'):
            for author in content['authors']:
                authors.append(author['name'])
        elif content.get('source') and content['source'].get('name'):
            authors.append(content['source']['name'])
        elif content.get('distributor') and content['distributor'].get('name'):
            authors.append(content['distributor']['name'])
        elif content.get('canonical_website'):
            authors.append(content['canonical_website'])
    if authors:
        item['author'] = {}
        if len(authors) == 1:
            item['author']['name'] = authors[0]
        else:
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    tags = []
    if content.get('taxonomy'):
        for key, val in content['taxonomy'].items():
            if isinstance(val, dict):
                if val.get('name'):
                    if not re.search('advertising|blocklists|EXCLUDE|INCLUDE|iptc-media|Safe from|TRBC', val['name']):
                        tags.append(val['name'])
                elif val.get('text'):
                    if not re.search('advertising|blocklists|EXCLUDE|INCLUDE|iptc-media|Safe from|TRBC', val['text']):
                        tags.append(val['text'])
            elif isinstance(val, list):
                for it in val:
                    if isinstance(it, dict):
                        if it.get('name'):
                            if not re.search('advertising|blocklists|EXCLUDE|INCLUDE|iptc-media|Safe from|TRBC', it['name']):
                                tags.append(it['name'])
                        elif it.get('text'):
                            if not re.search('advertising|blocklists|EXCLUDE|INCLUDE|iptc-media|Safe from|TRBC', it['text']):
                                tags.append(it['text'])
    if content.get('websites'):
        for key, val in content['websites'].items():
            if val.get('website_section') and val['website_section'].get('name'):
                if val['website_section']['name'] not in tags:
                    tags.append(val['website_section']['name'])
    if tags:
        item['tags'] = list(set(tags))

    if content.get('promo_items'):
        if content['promo_items'].get('basic') and not content['promo_items']['basic'].get('type'):
            item['_image'] = resize_image(content['promo_items']['basic'], site_json)
        elif content['promo_items'].get('basic') and content['promo_items']['basic']['type'] == 'image':
            item['_image'] = resize_image(content['promo_items']['basic'], site_json)
        elif content['promo_items'].get('basic') and content['promo_items']['basic']['type'] == 'gallery':
            item['_image'] = resize_image(content['promo_items']['basic']['promo_items']['basic'], site_json)
        elif content['promo_items'].get('basic') and content['promo_items']['basic']['type'] == 'video':
            item['_image'] = resize_image(content['promo_items']['basic']['promo_items']['basic'], site_json)
        elif content['promo_items'].get('images'):
            if content['promo_items']['images'][0] != None:
                item['_image'] = resize_image(content['promo_items']['images'][0], site_json)
    elif content.get('content_elements'):
        if content['content_elements'][0]['type'] == 'image':
            item['_image'] = resize_image(content['content_elements'][0], site_json)
        elif content['content_elements'][0]['type'] == 'video':
            if content['content_elements'][0].get('imageResizerUrls'):
                item['_image'] = utils.closest_dict(content['content_elements'][0]['imageResizerUrls'], 'width', 1000)
            elif content['content_elements'][0].get('promo_image'):
                item['_image'] = resize_image(content['content_elements'][0]['promo_image'], site_json)
    elif content.get('image'):
        item['_image'] = resize_image(content['image'], site_json)

    if content.get('description'):
        if isinstance(content['description'], str):
            item['summary'] = content['description']
        elif isinstance(content['description'], dict):
            item['summary'] = content['description']['basic']
    elif content.get('subheadlines') and content['subheadlines'].get('basic'):
        item['summary'] = content['subheadlines']['basic']

    if 'embed' in args and content['type'] != 'video':
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if content['type'] == 'gallery':
        item['_gallery'] = []
        item['content_html'] = '<h3><a href="{}/gallery?url={}" target="_blank">View photo gallery</a></h3>'.format(config.server, quote_plus(item['url']))
        item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
        for element in content['content_elements']:
            img_src = resize_image(element, site_json)
            thumb = resize_image(element, site_json, 800)
            desc = ''
            if element.get('subtitle'):
                desc = '<h4>' + element['subtitle'] + '</h4>'
            caption = ''
            credit = ''
            if element.get('credits_caption_display'):
                caption = element['credits_caption_display']
            else:
                if element.get('caption') and element['caption'] != '-':
                    caption = re.sub(r'^<p>|</p>$', '', element['caption'])
                if element.get('credits'):
                    if element['credits'].get('by') and element['credits']['by'][0].get('byline'):
                        if element['credits']['by'][0]['byline'] == 'Fanatics':
                            # Skip ad
                            img_src = ''
                        else:
                            credit = element['credits']['by'][0]['byline']
                    elif element['credits'].get('affiliation'):
                        credit = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in element['credits']['affiliation']]))
            if caption:
                desc += '<p>' + caption + '</p>'
            if img_src:
                item['content_html'] += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, credit, link=img_src, desc=desc) + '</div>'
                item['_gallery'].append({"src": img_src, "caption": credit, "desc": desc, "thumb": thumb})
        item['content_html'] += '</div>'
        return item
    else:
        item['content_html'] = get_content_html(content, url, args, site_json, save_debug)

    if content.get('label') and content['label'].get('read_it_at_url'):
        item['content_html'] += utils.add_embed(content['label']['read_it_at_url']['text'])

    return item


def get_content(url, args, site_json, save_debug=False):
    if not url.startswith('http'):
        return None
    split_url = urlsplit(url)
    if split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    paths = list(filter(None, split_url.path[1:].split('/')))

    if split_url.netloc == 'gray.video-player.arcpublishing.com':
        params = parse_qs(split_url.query)
        if not params.get('uuid'):
            logger.warning('unhandled url ' + url)
            return None
        api_url = 'https://gray-config-prod.api.arc-cdn.net/video/v1/ansvideos/findByUuid?uuid=' + params['uuid'][0]
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json[0], './debug/debug.json')
        return get_item(api_json[0], url, args, site_json, save_debug)
    elif split_url.netloc == 'www.washingtonpost.com' and '_video.html' in split_url.path:
        m = re.search(r'/([^/]+)_video.html$', split_url.path)
        api_url = 'https://video-api.washingtonpost.com/api/v1/ansvideos/findByUuid?uuid={}&domain=www.washingtonpost.com'.format(m.group(1))
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json[0], './debug/debug.json')
        return get_item(api_json[0], url, args, site_json, save_debug)

    for n in range(2):
        if split_url.netloc == 'www.washingtonpost.com' and '_story.html' in split_url.path:
            query = re.sub(r'\s', '', json.dumps(site_json['story']['query'])).replace('PATH', path)
            query = query.replace('"ALL_PATHS"', json.dumps({"all": paths}).replace(' ', ''))
            api_url = '{}{}?query={}&d={}&_website={}'.format(site_json['api_url'], site_json['story']['source'], quote_plus(query), site_json['deployment'], site_json['arc_site'])
        else:
            if 'galleries' in paths and 'gallery' in site_json:
                # https://www.cleveland.com/galleries/MWY2D3UWRRC6HMDMV6KQWI6ACM/
                query = re.sub(r'\s', '', json.dumps(site_json['gallery']['query'])).replace('PATH', path).replace('ID', paths[-1])
                api_url = '{}{}'.format(site_json['api_url'], site_json['gallery']['source'])
            else:
                query = re.sub(r'\s', '', json.dumps(site_json['content']['query'])).replace('PATH', path)
                api_url = '{}{}'.format(site_json['api_url'], site_json['content']['source'])
            # if re.search(r'ajc\.com|daytondailynews\.com|springfieldnewssun\.com', split_url.netloc):
            if '"ID"' in query:
                query = query.replace('ID', paths[-1])
            api_url += '?query={}&d={}&_website={}'.format(quote_plus(query), site_json['deployment'], site_json['arc_site'])
        if save_debug:
            logger.debug('getting content from ' + api_url)
        api_json = utils.get_url_json(api_url, site_json=site_json)
        if api_json:
            break
        elif n == 0:
            # Failed...try new deployment value
            d = get_deployment_value(url)
            if d > 0 and d != site_json['deployment']:
                logger.debug('retrying with new deployment value {}'.format(d))
                site_json['deployment'] = d
                utils.update_sites(url, site_json)
            else:
                return None
        else:
            return None

    if api_json.get('items'):
        content = api_json['items'][0]
    else:
        content = api_json

    if save_debug:
        utils.write_file(content, './debug/debug.json')

    if content.get('result'):
        return get_item(content['result'], url, args, site_json, save_debug)
    elif content.get('content'):
        return get_item(content['content'], url, args, site_json, save_debug)
    return get_item(content, url, args, site_json, save_debug)


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    paths = list(filter(None, path.split('/')))

    # https://www.baltimoresun.com/rss/
    # https://www.baltimoresun.com/arcio/rss/
    # https://feeds.washingtonpost.com/rss/business/technology/
    # https://www.washingtonpost.com/news/powerpost/feed/
    if 'rss' in paths or 'feed' in paths:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    for n in range(2):
        if len(paths) == 0:
            source = site_json['homepage_feed']['source']
            query = re.sub(r'\s', '', json.dumps(site_json['homepage_feed']['query']))
        elif re.search(r'about|author|auteur|autor|people|staff|team', paths[0]) or (len(paths) > 1 and paths[1].lower() == 'author'):
            author = ''
            if split_url.netloc == 'www.dlnews.com':
                authors_json = utils.get_url_json('https://api.dlnews.com/authors')
                if authors_json:
                    author_data = next((it for it in authors_json['data'] if it['slug'] == paths[1]), None)
                    if author_data:
                        author = author_data['id']
            elif split_url.netloc == 'www.leparisien.fr':
                # TODO: need the author name not the slug
                author = paths[-1].replace('-', ' ').title()
            elif paths[0] == 'about':
                # https://www.bostonglobe.com/about/staff-list/columnist/dan-shaughnessy/
                author = paths[-1]
            elif len(paths) > 1:
                if paths[1].lower() == 'author':
                    # https://www.thenationalnews.com/topics/Author/neil-murphy/
                    author = paths[-1]
                else:
                    # https://www.cleveland.com/staff/tpluto/posts.html
                    author = paths[1]
            else:
                # https://www.baltimoresun.com/bal-nathan-ruiz-20190328-staff.html
                m = re.search(r'(.*)-staff\.html', paths[0])
                if m:
                    author = m.group(1)
                else:
                    logger.warning('unhandled author url ' + args['url'])
                    return None
            if author:
                source = site_json['author_feed']['source']
                query = re.sub(r'\s', '', json.dumps(site_json['author_feed']['query'])).replace('AUTHOR', author).replace('PATH', path).replace('%20', ' ')
        elif paths[0] == 'tags' or paths[0] == 'tag' or paths[0] == 'topics' or (paths[0] == 'topic' and 'thebaltimorebanner' not in split_url.netloc):
            tag = paths[1]
            source = site_json['tag_feed']['source']
            query = re.sub(r'\s', '', json.dumps(site_json['tag_feed']['query'])).replace('TAG', tag).replace('PATH', path).replace('%20', ' ')
        elif split_url.netloc == 'www.reuters.com' and split_url.path.startswith('/markets/companies/'):
            tag = paths[-1]
            source = site_json['stock_symbol_feed']['source']
            query = re.sub(r'\s', '', json.dumps(site_json['stock_symbol_feed']['query'])).replace('SYMBOL', tag).replace('PATH', path).replace('%20', ' ')
        elif split_url.netloc == 'www.thedailybeast.com' and split_url.path.startswith('/cheat-sheet'):
            source = site_json['cheat-sheet']['source']
            query = re.sub(r'\s', '', json.dumps(site_json['cheat-sheet']['query']))
        else:
            if site_json.get('section_feed'):
                source = site_json['section_feed']['source']
                if 'washingtonpost' in split_url.netloc:
                    page_html = utils.get_url_html(args['url'])
                    if not page_html:
                        return None
                    query = ''
                    for m in re.findall(r'"_admin":({[^}]+})', page_html):
                        admin = json.loads(m)
                        if path in admin['alias_ids']:
                            query = '{{"query":"{}"}}'.format(re.sub(r'limit=\d+', 'limit=10', admin['default_content']))
                            break
                    if not query:
                        m = re.search(r'(prism://prism\.query/[^&]+)', page_html)
                        if m:
                            query = '{{"query":"{}"}}'.format(m.group(1) + '&limit=10')
                    if not query:
                        logger.warning('unknown feed for ' + args['url'])
                        return None
                else:
                    section = paths[-1]
                    if site_json['section_feed'].get('section_replace'):
                        for it in site_json['section_feed']['section_replace']:
                            section = section.replace(it[0], it[1])
                    section_path = path.replace('/section', '')
                    query = re.sub(r'\s', '', json.dumps(site_json['section_feed']['query'])).replace('SECTIONPATH', section_path).replace('SECTION', section).replace('PATH', path).replace('%20', ' ')
            elif site_json.get('sections') and site_json['sections'].get(paths[-1]):
                section = paths[-1]
                source = site_json['sections'][section]['source']
                query = re.sub(r'\s', '', json.dumps(site_json['sections'][section]['query'])).replace('SECTION', section).replace('PATH', path).replace('%20', ' ')

        api_url = '{}{}?query={}&d={}&_website={}'.format(site_json['api_url'], source, quote_plus(query), site_json['deployment'], site_json['arc_site'])
        if save_debug:
            logger.debug('getting feed from ' + api_url)

        feed_content = utils.get_url_json(api_url)
        if feed_content:
            break
        elif n == 0:
            # Failed...try new deployment value
            d = get_deployment_value(args['url'])
            if d > 0 and d != site_json['deployment']:
                logger.debug('retrying with new deployment value {}'.format(d))
                site_json['deployment'] = d
                utils.update_sites(args['url'], site_json)
            else:
                return None
        else:
            return None

    if save_debug:
        utils.write_file(feed_content, './debug/feed.json')

    feed_title = ''
    if isinstance(feed_content, dict):
        if split_url.netloc == 'www.thedailybeast.com' and split_url.path.startswith('/cheat-sheet'):
            content_elements = feed_content['cheatsheet']['content_elements']
        elif feed_content.get('content_elements'):
            content_elements = feed_content['content_elements']
        elif feed_content.get('stories'):
            content_elements = feed_content['stories']
        elif feed_content.get('result'):
            content_elements = feed_content['result']['articles']
            if feed_content['result'].get('section'):
                feed_title = 'Reuters > ' + feed_content['result']['section']['name']
        elif feed_content.get('latest'):
            content_elements = feed_content['latest']
        elif feed_content.get('items'):
            content_elements = feed_content['items']
    else:
        content_elements = feed_content

    n = 0
    items = []
    for content in content_elements:
        if content.get('canonical_url'):
            url = content['canonical_url']
        elif content.get('website_url'):
            url = content['website_url']
        elif content.get('url'):
            url = content['url']
        elif content.get('websites') and content['websites'].get(site_json['arc_site']) and content['websites'][site_json['arc_site']].get('website_url'):
            url = content['websites'][site_json['arc_site']]['website_url']

        if url.startswith('/'):
            url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, url)

        # Check age
        if args.get('age'):
            item = {}
            if content.get('first_publish_date'):
                date = content['first_publish_date']
            elif content.get('published_time'):
                date = content['published_time']
            elif content.get('display_date'):
                date = content['display_date']
            dt = datetime.fromisoformat(date.replace('Z', '+00:00'))
            item['_timestamp'] = dt.timestamp()
            if not utils.check_age(item, args):
                if save_debug:
                    logger.debug('skipping old article ' + url)
                continue
        if save_debug:
            logger.debug('getting content from ' + url)

        if not content.get('type'):
            item = get_content(url, args, site_json, save_debug)
        elif content.get('content_elements') and (content['content_elements'][0].get('content') or content['content_elements'][0]['type'] == 'image' or content['content_elements'][0]['type'] == 'video'):
            item = get_item(content, url, args, site_json, save_debug)
        elif content.get('type') and content['type'] == 'video' and content.get('streams'):
            item = get_item(content, url, args, site_json, save_debug)
        else:
            item = get_content(url, args, site_json, save_debug)

        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    if feed_title:
        feed['title'] = feed_title
    feed['items'] = items.copy()
    return feed



# TODO:
# custom_embed video clip:
#   https://www.clickorlando.com/news/local/2025/04/29/mount-doras-starry-night-home-gets-fresh-coat-of-paint-new-symbol-for-autism-awareness/
#   https://www.local10.com/news/local/2025/04/29/watch-live-broward-superintendent-gives-update-after-2nd-weapon-found-at-miramar-high-school/
#   https://www.clickondetroit.com/news/local/2025/04/30/detroit-strip-club-shut-down-over-video-of-kids-partying-inside-police-say/