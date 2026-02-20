import hashlib, math, random, re, uuid
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    clean_src = utils.clean_url(img_src)
    if 'images.radio.com' in clean_src:
        return '{}?width={}'.format(clean_src, width)
    return img_src


def get_content_type(content):
    if content.get('componentVariation'):
        return content['componentVariation']
    if content.get('_ref'):
        m = re.search(r'_components/([^/]+)/', content['_ref'])
        if m:
            return m.group(1)
    logger.warning('unable to determine content type for ' + content['_ref'])
    return ''


def render_content(content):
    content_html = ''
    content_type = get_content_type(content)

    if content_type == 'paragraph' or content_type == 'description':
        content_html += '<p>{}</p>'.format(content['text'])

    elif content_type == 'subheader':
        content_html += '<h3>{}</h3>'.format(content['text'])

    elif content_type == 'image' or content_type == 'feed-image':
        captions = []
        if content.get('caption'):
            captions.append(content['caption'])
        if content.get('credit'):
            captions.append(content['credit'])
        content_html += utils.add_image(resize_image(content['url']), ' | '.join(captions))

    elif content_type == 'youtube':
        content_html += utils.add_embed(content['origSource'])

    elif content_type == 'brightcove':
        content_html += utils.add_embed(content['seoEmbedUrl'])

    elif content_type == 'tweet':
        m = re.findall(r'(https:\/\/twitter\.com\/[^\/]+\/status/\d+)', content['html'])
        if m:
            content_html += utils.add_embed(m[-1])
        else:
            logger.warning('unable to determine tweet url')

    elif content_type == 'instagram-post':
        content_html += utils.add_embed(content['url'])

    elif content_type == 'omny':
        content_html += utils.add_embed(content['clipURL'])

    # elif content_type == 'podcast-episode-listen':
    #     content_html += add_podcast(content['selectedPodcast']['podcastData']['podcastId'], content['selectedPodcast']['podcastData']['episodeId'])

    elif content_type == 'html-embed':
        soup = BeautifulSoup(content['text'], 'html.parser')
        if soup.iframe and soup.iframe.get('src'):
            content_html += utils.add_embed(soup.iframe['src'])
        elif soup.div and soup.div.get('class') and 'infogram-embed' in soup.div['class']:
            content_html += utils.add_embed('https://infogram.com/' + soup.div['data-id'])
        else:
            logger.warning('unhandled contentVariation html-embed')

    elif re.search(r'inline-related|station-livestream-listen', content_type):
        pass

    else:
        logger.warning('unhandled contentVariation ' + content_type)

    return content_html


def make_aud_headers():
    # https://www.audacy.com/assets-a2/maina7fef96da064e66c7f69.js
    # function f() {
    #     var e = Date.now();
    #     return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (function(t) {
    #         var n = (e + 16 * Math.random()) % 16 | 0;
    #         return e = Math.floor(e / 16),
    #         ("x" === t ? n : 3 & n | 8).toString(16)
    #     }
    #     ))
    # }
    e = int(datetime.now(timezone.utc).timestamp() * 1000)
    correlation_id = ''
    for c in 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx':
        n = int((e + 16 * random.random()) % 16) | 0
        e = math.floor(e / 16)
        if c == 'x':
            correlation_id += hex(n)[2:]
        elif c == 'y':
            correlation_id += hex(3 & n | 8)[2:]
        else:
            correlation_id += c

    # with STPyV8.JSContext() as ctxt:
    #     ctxt.eval('''function p(e){for(var t,n,r=function(e,t){return e>>>t|e<<32-t},i=Math.pow,o=i(2,32),a="",s=[],l=8*e.length,c=p.h=p.h||[],u=p.k=p.k||[],d=u.length,f={},h=2;d<64;h++)if(!f[h]){for(t=0;t<313;t+=h)f[t]=h;c[d]=i(h,.5)*o|0,u[d++]=i(h,1/3)*o|0}for(e+="";e.length%64-56;)e+="\0";for(t=0;t<e.length;t++){if((n=e.charCodeAt(t))>>8)return"";s[t>>2]|=n<<(3-t)%4*8}for(s[s.length]=l/o|0,s[s.length]=l,n=0;n<s.length;){var v=s.slice(n,n+=16),g=c;for(c=c.slice(0,8),t=0;t<64;t++){var m=v[t-15],y=v[t-2],b=c[0],w=c[4],S=c[7]+(r(w,6)^r(w,11)^r(w,25))+(w&c[5]^~w&c[6])+u[t]+(v[t]=t<16?v[t]:v[t-16]+(r(m,7)^r(m,18)^m>>>3)+v[t-7]+(r(y,17)^r(y,19)^y>>>10)|0);(c=[S+((r(b,2)^r(b,13)^r(b,22))+(b&c[1]^b&c[2]^c[1]&c[2]))|0].concat(c))[4]=c[4]+S|0}for(t=0;t<8;t++)c[t]=c[t]+g[t]|0}for(t=0;t<8;t++)for(n=3;n+1;n--){var E=c[t]>>8*n&255;a+=(E<16?0:"")+E.toString(16)}return a}''')
    #     token = ctxt.eval('p("' + correlation_id + '")')
    token = hashlib.sha256(correlation_id.encode()).hexdigest()

    headers = {
        "accept": "*/*",
        "accept-language": "en-US",
        "aud-client-session-id": str(uuid.uuid4()),
        "aud-correlation-id": correlation_id,
        "aud-platform": "WEB",
        "aud-platform-variant": "NONE",
        "aud-user-token": 'f8k:' + token[3:35],
        "content-type": "application/json",
        "priority": "u=1, i",
        "sec-ch-ua": "\"Chromium\";v=\"128\", \"Not;A=Brand\";v=\"24\", \"Microsoft Edge\";v=\"128\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site"
    }
    return headers


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if paths[0] == 'stations' or paths[0] == 'podcast':
        headers = make_aud_headers()
        api_url = 'https://api.audacy.com/experience/v1/page?path=' + quote_plus(split_url.path) + '&marketIds=401-592|401-561|401-1277|401-7'
        print(api_url)
        page_json = utils.get_url_json(api_url, headers=headers)
        if not page_json:
            return None
        if save_debug:
            utils.write_file(page_json, './debug/debug.json')
        content_json = page_json['contentObj']
        if page_json.get('meta'):
            meta_json = page_json['meta']
        else:
            meta_json = None

        item = {}
        if page_json['type'] == 'EPISODE' or page_json['type'] == 'CHAPTER':
            item['id'] = content_json['id']
            if meta_json and meta_json.get('canonical'):
                item['url'] = meta_json['canonical']
            else:
                item['url'] = 'https://www.audacy.com' + content_json['url']
            if meta_json and meta_json.get('title'):
                item['title'] = meta_json['title']
            elif content_json.get('title'):
                item['title'] = content_json['title']
            dt = datetime.fromisoformat(content_json['publishDate'])
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt, date_only=True)
            if not item.get('title'):
                item['title'] = item['_display_date']
            item['author'] = {
                "name": content_json['parentShow']['title'],
                "url": 'https://www.audacy.com' + content_json['parentShow']['url']
            }
            if content_json.get('parentStation'):
                item['author']['name'] += ' (' + content_json['parentStation']['title'] + ')'
                item['author']['_display_name'] = '<a href="' + item['author']['url'] + '" target="_blank">' + item['author']['name'] + '</a> (<a href="https://www.audacy.com' + content_json['parentStation']['url'] + '" target="_blank">' + content_json['parentStation']['title'] + '</a>)'
            item['authors'] = []
            item['authors'].append(item['author'])

            if content_json['parentShow'].get('genres'):
                item['tags'] = content_json['parentShow']['genres'].copy()
            if content_json.get('description'):
                item['summary'] = content_json['description']
            item['image'] = content_json['parentImage']['square']
            if content_json['streamUrl'].get('m3u8'):
                item['_audio'] = content_json['streamUrl']['m3u8'].replace('.m3u8&', '.m3u8?')
                item['_audio_type'] = 'application/x-mpegURL'
            elif content_json['streamUrl'].get('default'):
                item['_audio'] = content_json['streamUrl']['default']
                item['_audio_type'] = 'audio/mpeg'
            attachment = {}
            attachment['url'] = item['_audio']
            attachment['mime_type'] = item['_audio_type']
            item['attachments'] = []
            item['attachments'].append(attachment)
            if content_json.get('durationSeconds'):
                item['_duration'] = utils.calc_duration(content_json['durationSeconds'])
            if content_json['entitySubtype'] == 'BROADCAST_SHOW_EPISODE':
                api_url = 'https://api.audacy.com/experience/v1/content/' + content_json['id'] + '/chapters'
                chapters_json = utils.get_url_json(api_url, headers=headers)
                if chapters_json:
                    if save_debug:
                        utils.write_file(chapters_json, './debug/podcast.json')
                    item['_playlist'] = []
                    item['_playlist_title'] = 'Chapters'
                    for chapter in chapters_json['chapters']:
                        item['_playlist'].append({
                            "src": re.sub(r'startTs=\d+', 'startTs=' + str(chapter['startOffset']), item['_audio']),
                            "mime_type": item['_audio_type'],
                            "title": chapter['title'],
                            "artist": '',
                            "duration": '',
                            "image": item['image']
                        })
            item['content_html'] = utils.format_audio_content(item, logo=config.logo_audacy)

        elif page_json['type'] == 'SHOW':
            item['id'] = content_json['id']
            if meta_json and meta_json.get('canonical'):
                item['url'] = meta_json['canonical']
            else:
                item['url'] = 'https://www.audacy.com' + content_json['url']
            if meta_json and meta_json.get('title'):
                item['title'] = meta_json['title']
            elif content_json.get('title'):
                item['title'] = content_json['title']
            if content_json.get('parentStation'):
                item['author'] = {
                    "name": content_json['parentStation']['title']
                }
                author = '<a href="https://www.audacy.com' + content_json['parentStation']['url'] + '" target="_blank">' + content_json['parentStation']['title'] + '</a>'
            else:
                item['author'] = {
                    "name": content_json['title']
                }
                author = ''
            item['authors'] = []
            item['authors'].append(item['author'])
            if content_json.get('genres'):
                item['tags'] = content_json['genres'].copy()
            if content_json.get('description'):
                item['summary'] = content_json['description']
            item['image'] = content_json['images']['square']
            # if 'embed' not in args and 'summary' in item:
            #     card_footer += '<p>' + item['summary'] + '</p>'
            api_url = 'https://api.audacy.com/experience/v1/content/{}/episodes?page=0&sort=DATE_DESC'.format(content_json['id'])
            episodes_json = utils.get_url_json(api_url, headers=headers)
            if episodes_json:
                if save_debug:
                    utils.write_file(episodes_json, './debug/podcast.json')
                item['_playlist'] = []
                item['_playlist_title'] = 'Episodes'
                for episode in episodes_json['results']:
                    dt = datetime.fromisoformat(episode['publishDate'])
                    if dt > datetime.now(timezone.utc):
                        continue
                    if 'date_published' not in item:
                        item['date_published'] = dt.isoformat()
                        item['_timestamp'] = dt.timestamp()
                        item['_display_date'] = utils.format_display_date(dt, date_only=True)
                    if episode.get('title'):
                        title = episode['title']
                    else:
                        title = utils.format_display_date(dt, date_only=True)
                    if episode['streamUrl'].get('default'):
                        audio_src = episode['streamUrl']['default']
                        audio_type = 'audio/mpeg'
                    elif episode['streamUrl'].get('m3u8'):
                        audio_src = episode['streamUrl']['m3u8']
                        audio_type = 'application/x-mpegURL'
                    item['_playlist'].append({
                        "src": audio_src,
                        "mime_type": audio_type,
                        "title": title,
                        "artist": '',
                        "duration": utils.calc_duration(episode['durationSeconds'], time_format=':'),
                        "image": episode['parentImage']['square']
                    })
            audio_src = config.server + '/playlist?url=' + quote_plus(item['url'])
            title = '<a href="' + item['url'] + '" target="_blank">' + item['title'] + '</a>'
            item['content_html'] = utils.format_audio_content(item, logo=config.logo_audacy)

        elif page_json['type'] == 'STATION':
            item['id'] = content_json['id']
            if meta_json and meta_json.get('canonical'):
                item['url'] = meta_json['canonical']
            else:
                item['url'] = 'https://www.audacy.com' + content_json['url']
            if meta_json and meta_json.get('title'):
                item['title'] = meta_json['title']
            elif content_json.get('title'):
                item['title'] = content_json['title']
            item['author'] = {
                "name": content_json['title']
            }
            item['authors'] = []
            item['authors'].append(item['author'])
            author =  '<a href="https://www.audacy.com"' + content_json['url'] + ' target="_blank">' + content_json['title'] + '</a>'
            if content_json.get('genres'):
                item['tags'] = content_json['genres'].copy()
            if content_json.get('description'):
                item['summary'] = content_json['description']
            item['image'] = content_json['images']['square']
            if content_json.get('streamUrl'):
                if content_json['streamUrl'].get('default'):
                    item['_audio'] = content_json['streamUrl']['default']
                    item['_audio_type'] = 'audio/mpeg'
                elif content_json['streamUrl'].get('m3u8'):
                    item['_audio'] = content_json['streamUrl']['m3u8']
                    item['_audio_type'] = 'application/x-mpegURL'
                elif content_json['streamUrl'].get('aac'):
                    item['_audio'] = content_json['streamUrl']['aac']
                    item['_audio_type'] = 'audio/aac'
                attachment = {}
                attachment['url'] = item['_audio']
                attachment['mime_type'] = item['_audio_type']
                item['attachments'] = []
                item['attachments'].append(attachment)
            if '_audio' in item:
                title = ''
                api_url = 'https://api.audacy.com/experience/v1/content/' + item['id'] + '/schedule'
                schedule_json = utils.get_url_json(api_url, headers=headers)
                if schedule_json:
                    for show in schedule_json['schedule']:
                        dt = datetime.now(timezone.utc)
                        dt_pub = datetime.fromisoformat(show['publishDate'])
                        dt_end = datetime.fromisoformat(show['endDateTime'])
                        if dt > dt_pub and dt < dt_end:
                            title = 'Now playing: <a href="https://www.audacy.com' + show['url'] + '" target="_blank">' + show['parentTitle'] + '</a>'
                            break
                audio_src = config.server + '/videojs?src=' + quote_plus(item['_audio']) + '&type=' + quote_plus(item['_audio_type']) + '&poster=' + quote_plus(item['image'])
                item['content_html'] = utils.add_audio_player(audio_src, item['image'], author, title, '')
            else:
                item['content_html'] = utils.add_audio_player('', item['image'], author, '', '')
    else:
        headers = {
            "accept": "application/json",
            "accept-language": "en-US,en;q=0.9,de;q=0.8",
            "sec-ch-ua": "\" Not A;Brand\";v=\"99\", \"Chromium\";v=\"99\", \"Microsoft Edge\";v=\"99\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "x-amphora-page-json": "true",
        }
        page_json = utils.get_url_json(utils.clean_url(url) + '?json', headers=headers)
        if not page_json:
            return None
        if save_debug:
            utils.write_file(page_json, './debug/debug.json')
        content_json = page_json['main'][0]

        item = {}
        item['id'] = content_json['_ref']
        item['url'] = content_json['canonicalUrl'].replace('http:', 'https:')
        item['title'] = content_json['headline']

        if content_json.get('firstPublishedDate'):
            dt = datetime.fromisoformat(content_json['firstPublishedDate']).astimezone(timezone.utc)
        else:
            dt = datetime.fromisoformat(content_json['date']).astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        if content_json.get('dateModified'):
            dt = datetime.fromisoformat(content_json['dateModified']).astimezone(timezone.utc)
            item['date_modified'] = dt.isoformat()

        item['authors'] = []
        for it in content_json['authors']:
            item['authors'].append({"name": it['name']})
        if len(item['authors']) > 0:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))

        if content_json.get('tags') and content_json['tags'].get('textTags'):
            item['tags'] = content_json['tags']['textTags'].copy()

        if content_json.get('feedImg'):
            item['image'] = content_json['feedImg']['url']
        elif content_json.get('feedImgUrl'):
            item['image'] = content_json['feedImgUrl']

        item['summary'] = content_json['pageDescription']

        item['content_html'] = ''
        if content_json.get('lead'):
            for content in content_json['lead']:
                item['content_html'] += render_content(content)

        for content in content_json['content']:
            item['content_html'] += render_content(content)
    return item


def get_feed(url, args, site_json, save_debug=False):
    # TODO
    return None