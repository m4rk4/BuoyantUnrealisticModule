import json, re
from bs4 import BeautifulSoup
import dateutil.parser
from dateutil import tz

from urllib.parse import quote_plus, urlencode, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def add_media(url, poster='', caption='', save_debug=False):
    media_html = ''
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if not paths[-1].endswith('.cms'):
        logger.warning('unhandled url ' + url)
        return media_html
    msid = paths[-1].replace('.cms', '')
    mediainfo_url = 'https://' + split_url.netloc + '/feeds/videomediainfo_v1/msid-' + msid +',feedtype-json.cms'
    media_info = utils.get_url_json(mediainfo_url)
    if not media_info:
        return media_html
    if save_debug:
        utils.write_file(media_info, './debug/media_info.json')
    if 'embedId' in media_info['item']:
        embed_id = media_info['item']['embedId']
    elif 'embed' in media_info['item']:
        embed_id = media_info['item']['embed']
    else:
        logger.warning('unknown video embed id in ' + mediainfo_url)
        return media_html
    params = {
        "vj": 105,
        "apikey": "etmweb46324htoi24",
        "k": embed_id,
        "mse": 1,
        "aj": 31,
        "ajbit": 0000,
        "pw": 699,
        "ph": 450,
        "chs": "undefined",
        "msid": msid,
        "url": url,
        "tpl": paths[-2],
        "sw": 1920,
        "sh": 1200,
        "cont": "playerContainer",
        "gdprn": 2,
        "skipanalytics": 2,
        "sdk": 1,
        "viewportvr": 100
    }
    mediainfo_url = 'https://tvid.in/api/mediainfo/' + embed_id[2:4] + '/' + embed_id[4:6] + '/' + embed_id + '/' + embed_id + '.json?' + urlencode(params)
    media_json = utils.get_url_json(mediainfo_url)
    if not media_json:
        return media_html
    if save_debug:
        utils.write_file(media_json, './debug/media.json')
    if not poster:
        poster = 'https:' + media_json['poster']
    if not caption:
        caption = media_json['name']
    if 'videodatetime' in media_info['item']:
        ist_tz = tz.gettz("Asia/Kolkata")
        dt = dateutil.parser.parse(media_info['item']['videodatetime'], tzinfos={"IST": ist_tz}).astimezone(tz.tzutc())
        date = utils.format_display_date(dt, True)
    else:
        date = ''
    if 'duration' in media_json:
        duration = utils.calc_duration(media_json['duration'], True)
    else:
        duration = ''
    if media_json['at'] == 'video':
        media = next((it for it in media_json['flavors'] if it['type'] == 'hls'), None)
        if media:
            media_type = 'application/x-mpegURL'
        else:
            media = utils.closest_dict([x for x in media_json['flavors'] if x['type'] == 'mp4'], 'bitrate', 1000)
            if media:
                media_type = 'video/mpr'
            else:
                logger.warning('unknown video source for ' + url)
        if media:
            media_html = utils.add_video('https:' + media['url'], media_type, poster, caption, use_videojs=True)
    elif media_json['at'] == 'audio':
        media = utils.closest_dict([x for x in media_json['flavors'] if x['type'] == 'mp3'], 'bitrate', 256)
        if media:
            media_type = 'audio/mpeg'
        else:
            media = next((it for it in media_json['flavors'] if it['type'] == 'hls'), None)
            if media:
                media_type = 'application/x-mpegURL'
            else:
                logger.warning('unknown audio source for ' + url)
        if media:
            media_html = utils.add_audio_v2('https:' + media['url'], poster, caption, url, media_json['vendor_name'], '', date, duration, media_type)
    return media_html


def format_node(node):
    node_html = ''
    end_tag = ''
    if node['node'] == 'text':
        node_html += node['text']
    elif node['node'] == 'element':
        if node['tag'] == 'a':
            node_html += '<a href="' + node['attr']['href'] + '"'
            if 'target' in node['attr']:
                node_html += ' target="' + node['attr']['target'] + '"'
            node_html += '>'
            end_tag = '</a>'
        elif node['tag'] == 'strong' or node['tag'] == 'strongwrap':
            node_html += '<strong>'
            end_tag = '</strong>'
        elif node['tag'] == 'em' or node['tag'] == 'emwrap':
            node_html += '<em>'
            end_tag = '</em>'
        elif node['tag'] == 'br':
            node_html += '<br>'
        elif node['tag'] == 'hr':
            node_html += '<hr style="margin:1em 0;">'
        elif node['tag'] == 'h2' or node['tag'] == 'h3' or node['tag'] == 'ul' or node['tag'] == 'ol' or node['tag'] == 'li':
            node_html += '<' + node['tag'] + '>'
            end_tag = '</' + node['tag'] + '>'
        elif node['tag'] == 'sup':
            node_html += '<h2>'
            end_tag = '</h2>'
        elif node['tag'] == 'img':
            node_html += utils.add_image(node['attr']['src'], node['attr'].get('agency'))
        elif node['tag'] == 'twitter':
            node_html += utils.add_embed('https://twitter.com/__/status/' + node['attr']['id'])
        elif node['tag'] == 'iframe':
            node_html += utils.add_embed(node['attr']['src'])
        elif node['tag'] == 'blockquote' and node.get('attr') and 'data-instgrm-permalink' in node['attr']:
            node_html += utils.add_embed(node['attr']['data-instgrm-permalink'])
            return node_html
        elif node['tag'] == 'etprimeblocker':
            node_html += '<h2 style="text-align:center;">ETPrime Exclusive Story</h2>'
        elif node['tag'] == 'div' and node.get('attr') and 'title' in node['attr'] and node['attr']['title'] == 'Instagram':
            pass
        elif node['tag'] == 'div' and node.get('attr') and 'class' in node['attr'] and node['attr']['class'] == 'Normal':
            pass
        elif node['tag'] == 'cdata' or node['tag'] == 'script':
            pass
        else:
            logger.warning('unhandled element tag ' + node['tag'])
    elif node['node'] == 'root':
        pass
    else:
        logger.warning('unhandled node ' + node['node'])
    if 'child' in node:
        for child in node['child']:
            node_html += format_node(child)
    node_html += end_tag
    return node_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    if not paths[-1].endswith('.cms'):
        logger.warning('unhandled url ' + url)
        return None
    msid = paths[-1].replace('.cms', '')
    if paths[-2] == 'primearticleshow':
        article_type = 'primearticle'
    else:
        article_type = 'article'
    api_url = 'https://etpwaapi.economictimes.com/request?type=' + article_type + '&msid=' + msid
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    article_json = None
    for it in api_json['searchResult']:
        if it['name'] == article_type:
            article_json = it['data']
            break
    if not article_json:
        logger.warning('unable to find article data for ' + url)
        return None

    item = {}
    item['id'] = msid
    # item['url'] = article_json['seo']['canonical']
    item['url'] = url
    item['title'] = article_json['title']

    ist_tz = tz.gettz("Asia/Kolkata")
    dt = dateutil.parser.parse(article_json['date'], tzinfos={"IST": ist_tz}).astimezone(tz.tzutc())
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('updated'):
        dt = dateutil.parser.parse(article_json['updated'], tzinfos={"IST": ist_tz}).astimezone(tz.tzutc())
        item['date_modified'] = dt.isoformat()

    item['authors'] =[{"name": x['title']} for x in article_json['authors']]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    else:
        item['author'] = {
            "name": article_json['agency']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

    item['tags'] = []
    if article_json['seo'].get('breadcrumb'):
        item['tags'] += [x['title'] for x in article_json['seo']['breadcrumb'] if 'url' in x]
    if article_json.get('relatedKeywords'):
        item['tags'] += [x['title'] for x in article_json['relatedKeywords']]
    elif article_json['seo'].get('keywords'):
        item['tags'] += [x.strip() for x in article_json['seo']['keywords'].split(',')]

    if article_json.get('img'):
        item['image'] = article_json['img']

    item['content_html'] = ''
    if article_json.get('artSummary'):
        item['summary'] = article_json['artSummary']
        if article_json['artSummary'].startswith('<p'):
            item['content_html'] += article_json['artSummary']
        else:
            item['content_html'] += '<p><em>' + article_json['artSummary'] + '</em></p>'
    elif article_json['seo'].get('description'):
        item['summary'] = article_json['seo']['description']

    if 'videoshow' in paths or 'podcast' in paths:
        item['content_html'] = add_media(item['url'], item['image'], item['title'], save_debug)
        if 'embed' in args:
            return item
        if 'summary' in item:
            item['content_html'] += '<p>' + item['summary'] + '</p>'
    elif 'slideshow' in paths:
        # slideshow_html = utils.get_url_html('https://economictimes.indiatimes.com/slideshow_slides.cms?msid=' + item['id'])
        slideshow_html = utils.get_url_html('https://economictimes.indiatimes.com/slideshow_slides.cms?msid=' + article_json['metainfo']['SourceID']['value'])
        if not slideshow_html:
            slideshow_html = utils.get_url_html(item['url'])
            if slideshow_html:
                soup = BeautifulSoup(slideshow_html, 'lxml')
                el = soup.find('meta', attrs={"property": "og:image"})
                if el:
                    m = re.search(r'msid-(\d+)', el['content'])
                    if m:
                        slideshow_html = utils.get_url_html('https://economictimes.indiatimes.com/slideshow_slides.cms?msid=' + m.group(1))
        if slideshow_html:
            if save_debug:
                utils.write_file(slideshow_html, './debug/debug.html')
            soup = BeautifulSoup(slideshow_html, 'html.parser')
            gallery_images = []
            gallery_html = ''
            for slide in soup.find_all('section', class_='slides'):
                img_src = 'https://img.etimg.com/photo/' + slide['data-msid'] + '.cms'
                thumb = 'https://img.etimg.com/thumb/msid-' + slide['data-msid'] + ',width-640,resizemode-4.cms'
                el = slide.find(class_='imgCourtesy')
                if el:
                    caption = el.decode_contents()
                else:
                    caption = ''
                desc = '<h3>'
                el = slide.find(class_='slidesCount')
                if el and el.get_text().strip():
                    desc += el.get_text().strip()
                el = slide.find('h2', attrs={"itemprop": "name"})
                if el and el.get_text().strip():
                    if desc != '<h3>':
                        desc += ': '
                    desc += el.decode_contents().strip()
                if desc == '<h3>':
                    desc = ''
                else:
                    desc += '</h3>'
                el = slide.select('p.s_des > caption')
                if el:
                    for it in el[0].find_all('br'):
                        it.decompose()
                    if el[0].get_text().strip():
                        desc += '<p>' + el[0].decode_contents().strip() + '</p>'
                gallery_images.append({"src": img_src, "caption": caption, "thumb": thumb, "desc": desc})
                gallery_html += utils.add_image(thumb, caption, link=img_src, desc=desc) + '<div>&nbsp;</div>'
            gallery_url = config.server + '/gallery?images=' + quote_plus(json.dumps(gallery_images))
            item['content_html'] = utils.add_image(item['image'], item['title'], link=gallery_url, overlay=config.gallery_button_overlay)
            # if 'embed' in args:
            #     return item
            item['content_html'] += '<h3><a href="' + gallery_url + '" target="_blank">View photo gallery</a></h3>' + gallery_html
    elif article_json.get('featuredvideo'):
        item['content_html'] += add_media(article_json['featuredvideo']['url'], '', article_json['featuredvideo']['imgcaption'], save_debug)
    elif article_json.get('img'):
        captions = []
        if article_json.get('imgcaption'):
            captions.append(re.sub(r'^<p>|</p>$', '', article_json['imgcaption']))
        if article_json.get('imgagency'):
            captions.append(article_json['imgagency'])
        item['content_html'] += utils.add_image(article_json['img'], ' | '.join(captions))

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if article_json.get('storyJSON'):
        item['content_html'] += format_node(article_json['storyJSON'])

    return item
