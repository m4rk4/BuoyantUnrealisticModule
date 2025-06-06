import html, json, re
import curl_cffi
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "priority": "u=0, i",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1"
    }
    r = curl_cffi.get(url, impersonate='chrome', headers=headers, proxies=config.proxies)
    if r.status_code != 200:
        logger.warning('status code {} getting {}'.format(r.status_code, url))
        return None
    page_html = r.text
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    page_soup = BeautifulSoup(page_html, 'lxml')
    el = page_soup.find('script', id='pageItemData')
    if not el:
        logger.warning('unable to find pageItemData in ' + url)
        return None

    page_data = json.loads(el.string)
    if save_debug:
        utils.write_file(page_data, './debug/debug.json')

    split_url = urlsplit(url)

    item = {}
    item['id'] = page_data['id']
    item['url'] = 'https://' + split_url.netloc + page_data['path']
    item['title'] = page_data['title']

    # TODO: difference between publicationTimestamp and originalPublicationTimestamp
    dt = datetime.fromisoformat(page_data['publicationTimestamp'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {
        "name": page_data['viewProperties']['analyticsModel']['authorName']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    if page_data.get('associatedRichTerms'):
        item['tags'] = [x['title'] for x in page_data['associatedRichTerms']]

    if page_data.get('primaryImage'):
        item['image'] = 'https://{}/.image/c_limit%2Ccs_srgb%2Cfl_progressive%2Cq_auto:good%2Cw_1200/{}/{}.{}'.format(split_url.netloc, page_data['primaryImage']['publicId'], page_data['primaryImage']['title'], page_data['primaryImage']['format'])

    if page_data.get('metaDescription'):
        item['summary'] = page_data['metaDescription']
    elif page_data.get('teaser'):
        item['summary'] = page_data['teaser']
    elif page_data.get('dek'):
        item['summary'] = page_data['dek']

    item['content_html'] = ''
    if page_data.get('dek'):
        item['content_html'] += '<p><em>' + page_data['dek'] + '</em></p>'

    body = page_soup.find(class_='m-detail--body')
    if body:
        el = page_soup.find(class_=['m-detail-header--media', 'm-detail--feature-container'])
        if el:
            body.insert(0, el)

        for el in body.find_all(['phoenix-super-link', 'script']):
            el.decompose()

        for el in body.find_all(class_=['m-in-content-ad-row', 'm-in-content-ad']):
            el.decompose()

        for el in body.find_all(id='action_button_container'):
            el.decompose()

        for el in body.find_all('a', attrs={"onclick": True}):
            del el['onclick']

        for el in body.select('p:has(> strong)'):
            if re.search(r'^(Next:|Related:|Sign up)', el.strong.get_text().strip(), flags=re.I):
                el.decompose()

        for el in body.find_all('div', recursive=False):
            new_html = ''
            if el.find('phoenix-picture'):
                it = el.find('img')
                if it:
                    paths = list(filter(None, urlsplit(it['data-src']).path[1:].split('/')))
                    img_src = 'https://{}/.image/c_limit%2Ccs_srgb%2Cfl_progressive%2Cq_auto:good%2Cw_1200/{}/{}'.format(split_url.netloc, paths[-2], paths[-1])
                    captions = []
                    it = el.find(class_='tml-image--caption')
                    if it:
                        captions.append(it.decode_contents())
                    it = el.find(class_='tml-image--attribution')
                    if it:
                        captions.append(it.decode_contents())
                    new_html = utils.add_image(img_src, ' | '.join(captions))
            elif el.find('phx-gallery-image'):
                if '_gallery' in item:
                    logger.warning('multiple galleries in ' + item['url'])
                item['_gallery'] = []
                new_html += '<h3><a href="{}/gallery?url={}" target="_blank">View photo gallery</a></h3>'.format(config.server, quote_plus(item['url']))
                new_html += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                for it in el.find_all('phx-gallery-image'):
                    img_src = it['data-full-src']
                    paths = list(filter(None, urlsplit(img_src).path[1:].split('/')))
                    thumb = 'https://{}/.image/c_limit%2Ccs_srgb%2Cfl_progressive%2Cq_auto:good%2Cw_640/{}/{}'.format(split_url.netloc, paths[-2], paths[-1])
                    if it.get('data-caption-html'):
                        caption = BeautifulSoup(html.unescape(it['data-caption-html']), 'html.parser').get_text()
                    else:
                        caption = ''
                    new_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img_src) + '</div>'
                    item['_gallery'].append({"src": img_src, "caption": caption, "thumb": thumb})
                new_html += '</div>'
            elif el.find('phoenix-video'):
                it = el.find('phoenix-video')
                new_html += utils.add_embed('https://cdn.jwplayer.com/v2/media/' + it['video-id'])
            # elif el.find('phoenix-exco-player'):
            #     player_url = 'https://player.ex.co/player/' + player_id
            #     player = utils.get_url_html(player_url)
            #     if not player:
            #         return None
            #     m = re.search(r'window\.STREAM_CONFIGS\[\'{}\'\] = (.*?);\n'.format(player_id), player)
            #     if not m:
            #         logger.warning('unable to find STREAM_CONFIGS in ' + player_url)
            #         return None
            #     stream_config = json.loads(m.group(1))
            #     utils.write_file(stream_config, './debug/video.json')
            #     new_html = utils.add_video(stream_config['contents'][0]['video']['mp4']['src'], 'video/mp4', stream_config['contents'][0]['poster'], stream_config['contents'][0]['title'])
            elif el.find('phoenix-twitter-embed'):
                new_html = utils.add_embed(el.find('phoenix-twitter-embed')['tweet-url'])
            elif el.find('phoenix-instagram-embed'):
                new_html = utils.add_embed(el.find('phoenix-instagram-embed')['src'])
            elif el.find('phoenix-tiktok-embed'):
                new_html = utils.add_embed(el.find('phoenix-tiktok-embed')['src'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled body item in ' + item['url'])
                print(str(el))

        item['content_html'] += body.decode_contents()
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
