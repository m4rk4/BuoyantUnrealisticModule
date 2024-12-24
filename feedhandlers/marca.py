import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def add_image(el_image, width=1200):
    img_src = ''
    it = el_image.find('source', attrs={"type": "image/jpeg"})
    if it and it.get('srcset'):
        img_src = utils.image_from_srcset(it['srcset'], width)
    else:
        it = el_image.find('img')
        if it and it.get('src'):
            img_src = it['src']
    if not img_src:
        logger.warning('unable to find image source')
        return ''
    captions = []
    it = el_image.find(class_='ue-c-article__media-description')
    if it:
        captions.append(it.get_text())
    it = el_image.find(class_='ue-c-article__media-source')
    if it:
        captions.append(it.get_text())
    return utils.add_image(img_src, ' | '.join(captions))


def add_video(el_video):
    m = re.search(r'/entry_id/([0-9a-z_]+)/', str(el_video), flags=re.I)
    if not m:
        logger.warning('unable to determine video id')
        return ''
    kp_url = 'https://k-vod.uecdn.es/html5/html5lib/v2.89.0_ue/mwEmbedFrame.php?&wid=_110&uiconf_id=14969339&entry_id={0}&flashvars[doubleClick]=%7B%22adTagUrl%22%3A%22https%3A%2F%2Fpubads.g.doubleclick.net%2Fgampad%2Fads%22%7D&flashvars[autoPlay]=true&flashvars[autoMute]=false&flashvars[mediaProxy]=%7B%22preferedFlavorBR%22%3Afalse%7D&flashvars[ueGacl]=US&flashvars[EmbedPlayer]=%7B%22UseDirectManifestLinks%22%3Atrue%2C%22skipAutoPlayMuted%22%3Atrue%7D&flashvars[strings]=%7B%22UNAUTHORIZED_COUNTRY%22%3A%22No%20puedes%20reproducir%20este%20contenido%20en%20tu%20territorio%20por%20motivo%20de%20geobloqueo%22%2C%22UNAUTHORIZED_COUNTRY_TITLE%22%3A%22Contenido%20no%20disponible%22%2C%22plugin%22%3Atrue%7D&flashvars[comScoreStreamingTag]=%7B%22plugin%22%3Atrue%2C%22asyncInit%22%3Atrue%2C%22c2%22%3A7184769%2C%22labelMapping%22%3A%22c3%3D%5C%22MARCA%5C%22%2Cns_st_pu%3D%5C%22MARCA%5C%22%2Cns_st_cu%3D%5C%22N%2FA%5C%22%2Cns_st_ty%3D%5C%22video%5C%22%2CdownloadUrl%3D%5C%22N%2FA%5C%22%2CdataUrl%3D%5C%22N%2FA%5C%22%22%7D&flashvars[thumbEmbedOrigin]=true&playerId=video-{0}&ServiceUrl=https%3A%2F%2Fak.uecdn.es&CdnUrl=https%3A%2F%2Fk-vod.uecdn.es&ServiceBase=%2Fapi_v3%2Findex.php%3Fservice%3D&UseManifestUrls=true&forceMobileHTML5=true&urid=2.89_ue&protocol=https'.format(m.group(1))
    kp_html = utils.get_url_html(kp_url)
    if not kp_html:
        return ''
    kp_soup = BeautifulSoup(kp_html, 'lxml')
    it = kp_soup.find('script', string=re.compile(r'window\.kalturaIframePackageData'))
    if not it:
        logger.warning('unable to find kalturaIframePackageData')
        return ''
    i = it.string.find('{')
    j = it.string.rfind('}')
    kp_data = json.loads(it.string[i:j + 1])
    utils.write_file(kp_data, './debug/video.json')
    # Use kp_data['entryResult']['meta']['downloadUrl'] for larger format
    poster = kp_data['entryResult']['meta']['thumbnailUrl'] + '/width/1200'
    return utils.add_video(kp_data['entryResult']['meta']['dataUrl'], 'video/mp4', poster, kp_data['entryResult']['meta']['name'])


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if split_url.path.startswith('/en') or split_url.netloc == 'us.marca.com':
        content_url = 'https://{}/ue-nydus/nydus.php?content={}'.format(split_url.netloc, split_url.path[1:].replace('.html', ''))
    elif split_url.path.startswith('/mx'):
        content_url = 'https://{}/mx/ue-nydus/nydus.php?content={}'.format(split_url.netloc, split_url.path[1:].replace('.html', ''))
    else:
        content_url = 'https://{}/nydus/nydus/http?content={}'.format(split_url.netloc, split_url.path[1:].replace('.html', ''))
    content_json = utils.get_url_json(content_url)
    if not content_json:
        return None
    if save_debug:
        utils.write_file(content_json, './debug/debug.json')

    item = {}
    item['id'] = content_json['global']['contentId']
    item['url'] = content_json['global']['url']
    item['title'] = content_json['analytics']['dataLayer']['be_page_article_title']

    dt = datetime.fromtimestamp(int(content_json['analytics']['dataLayer']['be_date_first_publication'])).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if content_json['ad'].get('customTargeting') and content_json['ad']['customTargeting'].get('tag'):
        item['tags'] = [x.strip() for x in content_json['ad']['customTargeting']['tag'].split(',')]

    item['image'] = content_json['global']['rrss']['imgUrl']

    soup = BeautifulSoup(content_json['content'], 'html.parser')
    if save_debug:
        utils.write_file(str(soup), './debug/debug.html')

    el = soup.find(class_='ue-c-article__byline-name')
    if el:
        item['author'] = {
            "name": el.get_text()
        }
        item['authors'] = []
        item['authors'].append(item['author'])

    item['content_html'] = ''
    if content_json['global']['rrss'].get('summary'):
        item['summary'] = content_json['global']['rrss']['summary']
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    el = soup.find(class_='ue-c-article__media--main-media')
    if el:
        if 'ue-c-article__media--video' in el['class']:
            item['content_html'] += add_video(el)
        else:
            item['content_html'] += add_image(el)

    body = soup.find(class_='ue-c-article__body')
    if body:
        for el in body.find_all(class_='ue-c-article__media--image'):
            new_html = add_image(el)
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()

        for el in body.find_all(class_='ue-c-article__media--video'):
            new_html = ''
            if re.search(r'kalturaPlayer', str(el)):
                new_html = add_video(el)
            elif re.search(r'dailymotion', str(el)):
                m = re.search(r'id="video-([^"]+)"', str(el))
                if m:
                    new_html = utils.add_embed('https://www.dailymotion.com/video/' + m.group(1), args={"embedder": item['url']})
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled ue-c-article__media--video in ' + item['url'])

        for el in body.find_all(class_='ue-c-article__embedded'):
            new_html = ''
            if el.find(class_='twitter-tweet'):
                it = el.find('a')
                new_html = utils.add_embed(it['href'])
            elif el.find(class_='instagram-media'):
                it = el.find('blockquote')
                new_html = utils.add_embed(it['data-instgrm-permalink'])
            else:
                it = el.find('iframe')
                if it and it.get('src'):
                    new_html = utils.add_embed(it['src'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled ue-c-article__embedded in ' + item['url'])

        for el in body.find_all('script'):
            el.decompose()

        item['content_html'] += body.decode_contents()
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
