import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlencode, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_photostory_content(url, args, site_json, save_debug):
    m = re.search(r'/(\d+)\.cms', url)
    if not m:
        logger.warning('unhandled url ' + url)
        return None
    api_url = 'https://global-feed.indiatimes.com/wufs/feed/show/photo?pc=toi&dm=t&msid={}&client=toi&pp=20'.format(m.group(1))
    content_json = utils.get_url_json(api_url)
    if not content_json:
        return None
    if save_debug:
        utils.write_file(content_json, './debug/debug.json')

    item = {}
    item['id'] = content_json['id']
    item['url'] = content_json['pwa_meta']['canonical']
    item['title'] = content_json['pwa_meta']['title']

    dt = datetime.fromisoformat(content_json['pwa_meta']['dlseo']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(content_json['pwa_meta']['luseo']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if content_json['metaInfo'].get('PhotographerByline'):
        item['author']['name'] = content_json['metaInfo']['PhotographerByline']
    elif content_json.get('agency') and content_json['agency'].get('name'):
        item['author']['name'] = content_json['agency']['name']
    elif content_json.get('ag'):
        item['author']['name'] = content_json['ag']
    elif content_json.get('createdby'):
        item['author']['name'] = content_json['createdby']
    else:
        item['author']['name'] = urlsplit(url).netloc
    item['authors'] = []
    item['authors'].append(item['author'])

    item['tags'] = [x['name'] for x in content_json['pwa_meta']['sec_hierarchy']]
    if content_json['pwa_meta'].get('key'):
        item['tags'] += [x.strip() for x in content_json['pwa_meta']['key'].split(',')]

    item['image'] = content_json['pwa_meta']['ogimg']

    item['summary'] = content_json['pwa_meta']['seodescription']

    gallery_images = []
    gallery_html = ''
    for i, it in enumerate(content_json['items']):
        img_src = 'https://static.toiimg.com/photo/{0}/{0}.jpg'.format(it['id'])
        thumb = 'https://static.toiimg.com/thumb/{}.jpg?imgsize={}&width=420&height={}&resizemode=76'.format(it['id'], it['imgsize'], int(420 * float(it['imgratio'])))
        caption = ''
        desc = ''
        if it.get('hl'):
            desc += '<h3>' + it['hl'] + '</h3>'
        if it.get('cap'):
            desc += re.sub(r'^null', '', it['cap'])
        if i == 0:
            gallery_html += utils.add_image(img_src, caption, link=img_src, desc=desc)
            gallery_html += '<div>&nbsp;</div><div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
        else:
            gallery_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img_src, desc=desc) + '</div>'
        gallery_images.append({"src": img_src, "caption": "", "desc": desc, "thumb": thumb})
    gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
    item['content_html'] = '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + gallery_html

    return item


def get_video_content(video_id, args, site_json, save_debug):
    video_url = 'https://timesofindia.indiatimes.com/feeds/videomediainfo_v1/msid-{},feedtype-json.cms'.format(video_id)
    #print(video_url)
    video_info = utils.get_url_json(video_url)
    if not video_id:
        return None
    if save_debug:
        utils.write_file(video_info, './debug/debug.json')

    if video_info['item']['agency'] == 'YouTube':
        return utils.get_content('https://www.youtube.com/watch?v=' + video_info['item']['embedId'], args, False)

    item = {}
    item['id'] = video_info['item']['id']
    item['url'] = 'https://timesofindia.indiatimes.com/{}/videoshow/{}.cms'.format(video_info['item']['seopath'], video_info['item']['id'])
    item['title'] = video_info['item']['title']

    tz_loc = pytz.timezone(config.local_tz)
    dt_loc = datetime.fromtimestamp(int(video_info['item']['timestamp']) / 1000)
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": video_info['item']['agency']}

    if video_info['item'].get('keyword'):
        item['tags'] = [it.strip() for it in video_info['item']['keyword'].split(',')]

    item['_image'] = 'https:' + video_info['item']['thumburl']

    if video_info['item'].get('description'):
        item['summary'] = video_info['item']['description']

    if video_info['item']['navsubsectionname'] == 'Etimes':
        api_key = 'toi371web5awj999ou6'
    else:
        api_key = 'toiweba5ec9705eb7ac2c984033e061'

    params = {
        "vj": 105,
        "apikey": api_key,
        "k": video_info['item']['embedId'],
        "mse": 1,
        "aj": 31,
        "ajbit": 0000,
        "pw": 699,
        "ph": 450,
        "chs": "undefined",
        "msid": item['id'],
        "url": item['url'],
        "tpl": "videoshow",
        "sw": 1920,
        "sh": 1200,
        "cont": "playerContainer",
        "gdprn": 2,
        "skipanalytics": 2,
        "sdk": 1,
        "viewportvr": 100
    }
    video_url = 'https://tvid.in/api/mediainfo/{0}/{1}/{2}/{2}.json?{3}'.format(video_info['item']['embedId'][2:4], video_info['item']['embedId'][4:6], video_info['item']['embedId'], urlencode(params))
    #print(video_url)
    video_json = utils.get_url_json(video_url)
    if not video_json:
        return ''
    if save_debug:
        utils.write_file(video_json, './debug/video.json')

    if video_json.get('name'):
        caption = video_json['name']
    else:
        caption = item['title']

    poster = 'https:' + video_json['poster']

    video = next((it for it in video_json['flavors'] if it['type'] == 'hls'), None)
    if video:
        item['_video'] = 'https:' + video['url']
        item['content_html'] = utils.add_video(item['_video'], 'application/x-mpegURL', poster, caption)
    else:
        video = utils.closest_dict(video_json['flavors'], 'bitrate', 1000)
        if video and video['type'] == 'mp4':
            item['_video'] = 'https:' + video['url']
            item['content_html'] = utils.add_video(item['_video'], 'video/mp4', poster, caption, use_videojs=True)
        else:
            logger.warning('unknown video source for ' + item['url'])
            return item

    if 'embed' not in args and item.get('summary'):
        item['content_html'] += '<p>{}</p>'.format(item['summary'])
    return item


def get_html_content(url, args, site_json, save_debug):
    # https://frontend-api-navik.indiatimes.com/v1/api/content/detail/643198?is_amp_story=1&locale_id=1
    m = re.search(r'(\d+)\.html', url)
    if not m:
        logger.warning('unhandled url ' + url)
        return None
    api_url = 'https://frontend-api-navik.indiatimes.com/v1/api/content/detail/{}?is_amp_story=1&locale_id=1'.format(m.group(1))
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    content_json = api_json['data']['content']
    item = {}
    item['id'] = content_json['content_id']
    item['url'] = 'https://' + urlsplit(url).netloc + content_json['guid']
    item['title'] = content_json['headline1']

    dt = datetime.fromisoformat(content_json['date_data']['publish_date_meta']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(content_json['date_data']['updated_at_meta']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['authors'] = [{"name": x['name']} for x in api_json['data']['authors']]
    item['author'] = {
        "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
    }

    item['tags'] = []
    if content_json.get('categories'):
        item['tags'] += [x['name'] for x in content_json['categories']]
    if content_json.get('tags'):
        item['tags'] += [x['name'] for x in content_json['tags']]

    item['content_html'] = ''
    if content_json.get('summary'):
        item['summary'] = content_json['summary']
        item['content_html'] += '<p><em>' + item['summary'] + '</em></p>'

    if content_json.get('media'):
        for it in content_json['media']:
            if it['path'].startswith('/content/'):
                item['image'] = 'https://im.indiatimes.in' + it['media_path']
                item['content_html'] += utils.add_image(item['image'], it.get('credits'))
                break

    soup = BeautifulSoup(api_json['data']['detail']['description'], 'html.parser')
    for el in soup.find_all('blockquote', class_='instagram-media'):
        new_html = utils.add_embed(el['data-instgrm-permalink'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all('blockquote', class_='reddit-embed-bq'):
        new_html = utils.add_embed(el.a['href'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(['script', 'style']):
        el.decompose()

    item['content_html'] += str(soup)
    return item


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if paths[-1].endswith('.html'):
        return get_html_content(url, args, site_json, save_debug)
    elif paths[-2] == 'videoshow':
        return get_video_content(paths[-1].split('.')[0], args, site_json, save_debug)
    elif paths[-2] == 'photostory':
        return get_photostory_content(url, args, site_json, save_debug)

    api_url = 'https://toifeeds.indiatimes.com/treact/feeds/toi/web/show/news?version=v2&path=/{}/{}'.format(paths[-2], paths[-1])
    print(api_url)
    content_json = utils.get_url_json(api_url, user_agent='facebook')
    if not content_json:
        return None
    if save_debug:
        utils.write_file(content_json, './debug/debug.json')

    item = {}
    item['id'] = content_json['id']
    item['url'] = content_json['seo']['canonical']
    item['title'] = content_json['hl']

    dt = datetime.fromisoformat(content_json['seo']['datePublished']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(content_json['seo']['dateModified']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['authors'] = []
    if content_json.get('authors'):
        item['authors'] = [{"name": x['name']} for x in content_json['authors']]
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    elif content_json.get('ag'):
        item['author'] = {
            "name": content_json['ag']
        }
        item['authors'].append(item['author'])
    elif content_json.get('getAuthorWidgetDetails') and content_json['getAuthorWidgetDetails'].get('name'):
        item['author'] = {
            "name": content_json['getAuthorWidgetDetails']['name']
        }
        item['authors'].append(item['author'])
    else:
        logger.warning('unknown author for ' + item['url'])

    if content_json.get('kws'):
        item['tags'] = [it.strip() for it in content_json['kws'].split(',')]

    if content_json.get('des'):
        item['summary'] = content_json['des']

    item['content_html'] = ''
    if content_json.get('syn'):
        item['content_html'] = '<p><em>{}</em></p>'.format(content_json['syn'])

    if content_json.get('videos'):
        item['_image'] = 'https://static.toiimg.com/photo/{}.cms'.format(content_json['videos'][0]['id'])
        #item['content_html'] += add_video(content_json['videos'][0])
        video_item = get_video_content(content_json['videos'][0]['id'], {"embed": True}, site_json, False)
        if video_item:
            item['content_html'] += video_item['content_html']
    elif content_json.get('images'):
        if len(content_json['images']) == 1:
            image = content_json['images'][0]
        else:
            image = next((it for it in content_json['images'] if it.get('payload') and it['payload'] == 'OverrideLeadImage'), None)
            if not image:
                image = next((it for it in content_json['images'] if it.get('payload') and it['payload'] == 'mobileleadimage'), None)
                if not image:
                    image = content_json['images'][0]
        item['_image'] = 'https://static.toiimg.com/photo/{}.cms'.format(image['id'])
        item['content_html'] += utils.add_image(item['_image'], image.get('cap'))

    if content_json.get('cs') and content_json['cs'] == 'prime':
        for it in content_json['schema']:
            schema = json.loads(it)
            if schema.get('@type') and schema['@type'] == 'NewsArticle' and schema.get('articleBody'):
                utils.write_file(schema, './debug/schema.json')
                def sub_add_medium(matchobj):
                    img_src = 'https://static.toiimg.com/photo/{}.cms'.format(matchobj.group(1))
                    return '</p>' + utils.add_image(img_src) + '<p>'
                article_body = '<p>{}</p>'.format(re.sub(r'medium(\d+)', sub_add_medium, schema['articleBody']))
                article_body = re.sub(r'([a-z]\.)([A-Z])', r'\1</p><p>\2', article_body)
                #article_body = re.sub(r'<p>([^<]+?[a-z])(?=[A-Z])([^<]+?)<\/p>', r'<h3>\1</h3><p>\2</p>', article_body)
                item['content_html'] += article_body
                return item

    p = False
    for content in content_json['story']:
        if content['tn'] == 'text':
            if not p:
                item['content_html'] += '<p>'
                p = True
            if content.get('tags'):
                item['content_html'] += '<{0}>{1}</{0}>'.format(content['tags'], content['value'])
            else:
                item['content_html'] += content['value']
        elif content['tn'] == 'link':
            if not p:
                item['content_html'] += '<p>'
                p = True
            item['content_html'] += '<a href="{}">{}</a>'.format(content['wu'], content['value'])
        elif content['tn'] == 'keyword' and content.get('wu'):
            if not p:
                item['content_html'] += '<p>'
                p = True
            item['content_html'] += '<a href="{}">{}</a>'.format(content['wu'], content['value'])
        elif content['tn'] == 'cdata' and content['value'].startswith('<b>'):
            if not p:
                item['content_html'] += '<p>'
                p = True
            item['content_html'] += content['value']
        elif content['tn'] == 'cdata' and (content['value'].startswith('<h2>') or content['value'].startswith('<ul>') or content['value'].startswith('<table')):
            if p == True:
                item['content_html'] += '</p>'
                p = False
            item['content_html'] += content['value']
        elif content['tn'] == 'br':
            if p == True:
                item['content_html'] += '</p>'
                p = False
        elif content['tn'] == 'inlineimage':
            if p == True:
                item['content_html'] += '</p>'
                p = False
            image_id = content['imageId'].split('&')[0]
            item['content_html'] += utils.add_image('https://static.toiimg.com/photo/{}.cms'.format(image_id), content.get('cap'))
        elif content['tn'] == 'inlinevideo':
            if p == True:
                item['content_html'] += '</p>'
                p = False
            if content.get('playerType') and content['playerType'] == 'youtube':
                item['content_html'] += utils.add_embed('https://www.youtube.com/watch?v=' + content['id'])
            else:
                video_item = get_video_content(content['id'], {"embed": True}, site_json, False)
                if video_item:
                    item['content_html'] += video_item['content_html']
        elif content['tn'] == 'cdata' and 'twitter-tweet' in content['value']:
            if p == True:
                item['content_html'] += '</p>'
                p = False
            m = re.findall(r'href="([^"]+)"', content['value'])
            item['content_html'] += utils.add_embed(m[-1])
        elif content['tn'] == 'cdata' and 'instagram-media' in content['value']:
            if p == True:
                item['content_html'] += '</p>'
                p = False
            m = re.search(r'data-instgrm-permalink="([^"]+)"', content['value'])
            item['content_html'] += utils.add_embed(m.group(1))
        elif content['tn'] == 'extquote':
            if p == True:
                item['content_html'] += '</p>'
                p = False
            quote = ''
            if content.get('au'):
                quote += '<strong>{}</strong><br/>'.format(content['au'])
            quote += content['value']
            item['content_html'] += utils.add_blockquote(quote)
        elif content['tn'] == 'summarizedstory':
            item['content_html'] += '<div style="font-weight:bold;"><a href="{}">{}</a></div><p>{}</p>'.format(content['su'], content['value'], content['syn'])
        elif content['tn'] == 'jarvisAd' or content['tn'] == 'hindsight_ad_code' or content['tn'] == 'readalso':
            if p == True:
                item['content_html'] += '</p>'
                p = False
            continue
        elif content['tn'] == 'slider' and content['name'] == 'Briefs slider':
            if p == True:
                item['content_html'] += '</p>'
                p = False
            continue
        else:
            logger.warning('unhandled content type {} in {}'.format(content['tn'], item['url']))
    if p == True:
        item['content_html'] += '</p>'
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
