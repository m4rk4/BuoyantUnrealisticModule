import base64, copy, html, json, re
import curl_cffi, certifi
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import breport, datawrapper

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200, crop='original'):
    split_url = urlsplit(img_src)
    if split_url.netloc == 'dynaimage.cdn.cnn.com':
        paths = list(filter(None, split_url.path[1:].split('/')))
        return 'https://dynaimage.cdn.cnn.com/{}/q_auto,w_{},c_fit/{}'.format('/'.join(paths[:-2]), width, paths[-1])
    return split_url.scheme + '://' + split_url.netloc + split_url.path + '?c=' + crop + '&q=w_' + str(width) + ',c_fill/f_avif'


def get_resized_image(image_cuts, width=1000):
    images = []
    for key, img in image_cuts.items():
        if img['uri'].startswith('https://dynaimage.cdn.cnn.com'):
            return resize_image(img['uri'], width)
        images.append(img)
    img = utils.closest_dict(images, 'width', width)
    if img['uri'].startswith('//'):
        img_src = 'https:' + img['uri']
    else:
        img_src = img['uri']
    return img_src


def add_image(image, width=1000):
    captions = []
    el = image.find(class_=re.compile(r'^image_.*_credit$'))
    if el and el.get_text().strip():
        captions.append(el.decode_contents())
        el.decompose()
    el = image.find(attrs={"data-editable": "metaCaption"})
    if el and el.get_text().strip():
        captions.insert(0, el.decode_contents())
    else:
        el = image.find(attrs={"itemprop": "caption"})
        if el and el.get_text().strip():
            captions.insert(0, el.get_text().strip())
    return utils.add_image(resize_image(image['data-url']), ' | '.join(captions))


def get_video_info_json(video_id, save_debug=False):
    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "sec-ch-ua": "\"Chromium\";v=\"110\", \"Not A(Brand\";v=\"24\", \"Microsoft Edge\";v=\"110\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36 Edg/110.0.1587.57"
    }
    video_url = 'https://fave.api.cnn.io/v1/video?id={}&customer=cnn&edition=domestic&env=prod'.format(video_id)
    video_json = utils.get_url_json(video_url, headers=headers)
    if not video_json:
        logger.warning('unable to get video info from ' + video_url)
        return None
    if save_debug:
        utils.write_file(video_json, './debug/video.json')
    return video_json


def process_element(element):
    element_html = ''
    element_contents = None
    if element.get('elementContents'):
        element_contents = element['elementContents']
        if isinstance(element['elementContents'], dict):
            if element['elementContents'].get('type'):
                element_contents = element['elementContents'][element['elementContents']['type']]

    if re.search('article|featured-video-collection|myfinance|read-more', element['contentType']):
        pass

    elif element['contentType'] == 'sourced-paragraph':
        element_html += '<p>'
        if element_contents.get('location') or element_contents.get('source'):
            element_html += '<b>'
        if element_contents.get('location'):
            element_html += element_contents['location']
        if element_contents.get('source'):
            if element_contents.get('location'):
                element_html += '&nbsp;'
            element_html += '({})'.format(element_contents['source'])
        if element_contents.get('location') or element_contents.get('source'):
            element_html += '&nbsp;&ndash;&nbsp;</b>&nbsp;'
        for text in element_contents['formattedText']:
            element_html += text
        element_html += '</p>'

    elif element['contentType'] == 'editorial-note':
        element_html += '<div style="border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px; font-style:italic;"><b>Editor\'s note:</b> '
        for text in element_contents:
            element_html += text
        element_html += '</div>'

    elif element['contentType'] == 'factbox':
        if not re.search(r'get our free|sign up', element_contents['title'], flags=re.I):
            element_html += '<blockquote><b>{}</b><br>'.format(element_contents['title'])
            for text in element_contents['text']:
                element_html += text['html'][0]
            element_html += '</blockquote>'

    elif element['contentType'] == 'pullquote':
        element_html += '<blockquote><b>{}</b><br> &ndash; {}</blockquote>'.format(element_contents['quote'], element_contents['author'])

    elif element['contentType'] == 'raw-html':
        if re.search(r'\bjs-cnn-erm\b|Click to subscribe|float:left;|float:right;', element_contents['html'], flags=re.I):
            pass
        else:
            raw_soup = BeautifulSoup(element_contents['html'], 'html.parser')
            if raw_soup.video:
                it = raw_soup.find(class_=re.compile(r'cap_\d+'))
                if it:
                    caption = it.get_text()
                else:
                    caption = ''
                element_html += utils.add_video('https:' + raw_soup.source['src'], raw_soup.source['type'], 'https:' + raw_soup.video['poster'], caption)
            else:
                element_html += re.sub(r'(\/\/[^\.]*.cnn\.com)', r'https:\1', element_contents['html'])

    elif element['contentType'] == 'image' or element['contentType'] == 'map':
        img_src = get_resized_image(element_contents['cuts'])
        captions = []
        if element_contents.get('caption'):
            captions.append(element_contents['caption'])
        if element_contents.get('photographer'):
            captions.append(element_contents['photographer'])
        elif element_contents.get('source'):
            captions.append(element_contents['source'])
        element_html += utils.add_image(img_src, ' | '.join(captions))

    elif element['contentType'] == 'gallery-full':
        for content in element_contents:
            if content['contentType'] == 'image':
                img_src = get_resized_image(content['elementContents']['cuts'])
                if content['elementContents'].get('caption'):
                    desc = content['elementContents']['caption'][0]
                else:
                    desc = ''
                if content['elementContents'].get('photographer'):
                    caption = content['elementContents']['photographer']
                elif content['elementContents'].get('source'):
                    caption = content['elementContents']['source']
                else:
                    caption = ''
                element_html += utils.add_image(img_src, caption, desc=desc)

    elif element['contentType'] == 'video-demand':
        video_info = get_video_info_json(element_contents['videoId'])
        if video_info:
            video_src = ''
            for vid in video_info['files']:
                if 'mp4' in vid['bitrate']:
                    video_src = vid['fileUri']
                    video_type = 'video/mp4'
                    break
            if video_src:
                caption = ''
                if video_info.get('headline'):
                    caption += video_info['headline'].strip()
                if video_info.get('description'):
                    if caption and not caption.endswith('.'):
                        caption += '. '
                    caption += video_info['description'].strip()

                for img in reversed(video_info['images']):
                    poster = img['uri']
                    if img['name'] == '640x360':
                        break
                element_html += utils.add_video(video_src, video_type, poster, caption)

    elif element['contentType'] == 'animation':
        video_src = re.sub(r'w_\d+', 'w_640', element['elementContents']['cuts']['medium']['uri'])
        element_html += utils.add_video(video_src, 'video/mp4', video_src.replace('.mp4', '.jpg'))

    elif element['contentType'] == 'youtube':
        if element_contents.get('embedUrl'):
            element_html += utils.add_embed(element_contents['embedUrl'])
        elif element_contents.get('embedHtml'):
            element_html += utils.add_youtube(element_contents['embedHtml'])
        else:
            logger.warning('unhandled contentType youtube')

    elif element['contentType'] == 'instagram':
        if element_contents.get('embedUrl'):
            element_html += utils.add_embed(element_contents['embedUrl'])
        else:
            logger.warning('unhandled contentType instagram')
            #element_html += utils.add_instagram(element_contents['embedHtml'])

    elif element['contentType'] == 'twitter':
        if element_contents.get('embedUrl'):
            element_html += utils.add_embed(element_contents['embedUrl'])
        else:
            m = re.findall(r'(https:\/\/twitter\.com\/[^\/]+\/status/\d+)', element_contents['embedHtml'])
            if m:
                element_html += utils.add_embed(m[-1])
            else:
                logger.warning('unhandled contentType twitter')

    else:
        logger.warning('unhandled contentType ' + element['contentType'])
    return element_html


def format_page_contents(page_contents, item):
    first_element = True
    content_html = ''
    for pages in page_contents:
        for page in pages:
            if page:
                for zone in page['zoneContents']:
                    if isinstance(zone, list):
                        if len(zone) >= 1 and zone[0]:
                            content_html += '<p>'
                            for z in zone:
                                content_html += z
                            content_html += '</p>'
                        continue
                    if zone.get('type'):
                        # Note: "containers" seem to be ads, related articles, etc.
                        if zone['type'] == 'element':
                            # Remove the feed image if there's a lead photo/video
                            if first_element:
                                if re.search(r'^(gallery|image|video)', zone['contentType']):
                                    item['_image'] = item['image']
                                    del item['image']
                            else:
                                if item.get('image'):
                                    content_html += utils.add_image(item['image'])
                                    item['_image'] = item['image']
                                    del item['image']
                            content_html += process_element(zone)
                            first_element = False
                    else:
                        if zone.get('formattedText'):
                            for text in zone['formattedText']:
                                content_html += '<p>{}</p>'.format(text)
    return content_html


def get_item_info(article_json, save_debug=False):
    item = {}
    item['id'] = article_json['sourceId']
    item['url'] = article_json['canonicalUrl']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['firstPublishDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['lastPublishDate'])
    item['date_modified'] = dt.isoformat()

    author = ''
    if isinstance(article_json['bylineProfiles'], list):
        byline_profiles = article_json['bylineProfiles']
    else:
        byline_profiles = article_json['bylineProfiles'][article_json['bylineProfiles']['type']]
    if len(byline_profiles) > 0:
        authors = []
        for byline in byline_profiles:
            authors.append(byline['name'])
        item['author'] = {}
        if authors:
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
        else:
            item['author']['name'] = 'CNN'
    else:
        item['author'] = {}
        item['author']['name'] = re.sub(r', CNN.*$', '', article_json['bylineText'])

    if article_json.get('metaKeywords'):
        tags = article_json['metaKeywords'].replace(article_json['title'] + ' - CNN', '').strip()
        if tags.endswith(','):
            tags = tags[:-1]
        item['tags'] = [tag.strip() for tag in tags.split(',')]

    item['image'] = 'https:' + article_json['metaImage']
    item['summary'] = article_json['description']
    return item


def get_gallery_images(component):
    gallery_images = []
    for it in component['slides']:
        captions = []
        if it['metadata'].get('caption'):
            captions.append(it['metadata']['caption'])
        elif component.get('galleryCaption'):
            captions.append(component['galleryCaption'])
        if it['metadata'].get('credit'):
            captions.append(it['metadata']['credit'])
        elif component.get('galleryCredit'):
            captions.append(component['galleryCredit'])
        gallery_images.append({"src": it['url'], "caption": " | ".join(captions), "thumb": resize_image(it['url'], 640)})
    return gallery_images


def format_component(component):
    component_type = urlsplit(component['_ref']).path.strip('/').split('/')[2]
    component_html = ''
    if component_type == 'paragraph':
        component_html = '<p>' + component['text'] + '</p>'
    elif component_type == 'subheader':
        if component.get('text'):
            if component['type'] == 'h5' or component['type'] == 'h6':
                component_html = '<h4>' + component['text'] + '</h4>'
            else:
                component_html = '<{0}>{1}</{0}>'.format(component['type'], component['text'])
    elif component_type == 'list':
        component_html = '<' + component['listType'] + '>'
        for it in component['items']:
            component_html += '<li>' + it['text'] + '</li>'
        component_html += '</' + component['listType'] + '>'        
    elif component_type == 'pull-quote':
        if component['componentVariation'] == 'pull-quote_block-quote':
            if component['attribution']:
                caption = '<br><br>&ndash ' + component['attribution']
            else:
                caption = ''
            component_html = utils.add_blockquote(component['text'] + caption, False)
        elif component['componentVariation'] == 'pull-quote':
            component_html = utils.add_pullquote(component['text'], component['attribution'])
        else:
            logger.warning('unhandled pull-quote componentVariation ' + component['componentVariation'] + ' in ' + component['_ref'])
    elif component_type == 'image':
        captions = []
        if component['metadata'].get('caption'):
            captions.append(component['metadata']['caption'])
        if component['metadata'].get('credit'):
            captions.append(component['metadata']['credit'])
        if component['componentVariation'] == 'image_expandable':
            component_html = utils.add_image(resize_image(component['url']), ' | '.join(captions), link=component['url'], fig_style='margin:0; padding:0;')
        else:
            component_html = utils.add_image(resize_image(component['url']), ' | '.join(captions))
    elif component_type == 'gallery-inline':
        gallery_images = get_gallery_images(component)
        if 'canonicalUrlPath' in component:
            if '/gallery/' in component['canonicalUrlPath']:
                gallery_url = config.server + '/gallery?url=' + quote_plus('https://www.cnn.com/' + component['canonicalUrlPath'])
            else:
                gallery_url = ''
            gallery_caption = 'Gallery: <a href="https://www.cnn.com' + component['canonicalUrlPath'] + '" target="_blank">' + component['headline'] + '</a>'
            if component.get('galleryCredit'):
                gallery_caption += ' | ' + component['galleryCredit']
            elif component.get('metadata') and component['metadata'].get('credit'):
                gallery_caption += ' | ' + component['metadata']['credit']
            component_html += utils.add_gallery(gallery_images, gallery_url, gallery_caption, show_gallery_poster=True)
        else:
            aspect_ratio = '{}/{}'.format(component['slides'][0]['width'], component['slides'][0]['height'])
            gallery_caption = component['headline']
            if component['metadata'].get('credit'):
                gallery_caption += ' | ' + component['metadata']['credit']
            elif component.get('galleryCredit'):
                gallery_caption += ' | ' + component['galleryCredit']
            component_html += utils.add_carousel(gallery_images, aspect_ratio, gallery_caption)
    elif component_type == 'video-inline' or component_type == 'video-resource':
        if 'contentType' in component and component['contentType'] == 'live-stream':
            # TODO: get live stream video url
            component_html = utils.add_image(resize_image(component['thumbnails'][0]['url']), component['headline'], link='https://www.cnn.com/videos/live', overlay=config.video_button_overlay)
        else:
            if component['componentVariation'].startswith('video-inline'):
                video = component['featuredVideo']
            else:
                video = component
            poster = resize_image(video['thumbnail'][0]['url'], 1280)
            asset = next((it for it in video['assetUrls'] if it['type'] == 'm3u8'), None)
            if asset:
                component_html = utils.add_video(asset['url'], 'application/x-mpegURL', poster, video['headline'])
            else:
                asset = next((it for it in video['assetUrls'] if it['type'] == 'mp4'), None)
                if asset:
                    component_html = utils.add_video(asset['url'], 'video/mp4', poster, video['headline'])
                else:
                    logger.warning('unknown video type for ' + component['_ref'])
    elif component_type == 'interactive-video' and component['mimeType'] == 'video/mp4':
        poster = resize_image(component['url'], 1280)
        captions = []
        if component['metadata'].get('caption'):
            captions.append(component['metadata']['caption'])
        if component['metadata'].get('credit'):
            captions.append(component['metadata']['credit'])
        component_html = utils.add_video(component['url'], component['mimeType'], poster, ' | '.join(captions))
    elif component_type == 'graphic':
        if component['graphicType'] == 'dailygraphic':
            component_html = utils.add_image(config.server + '/screenshot?viewport=800%2C800&waitfortime=5000&url=' + quote_plus(component['url']), link=component['url'])
        elif component['graphicType'] == 'datawrapper':
            component_html = utils.add_embed('https://ix.cnn.io/charts/' + component['chartId'])
        else:
            logger.warning('unhandled graphic type ' + component['graphicType'] + ' in ' + component['_ref'])
    elif component_type == 'instagram' or component_type == 'tiktok' or component_type == 'twitter' or component_type == 'youtube':
        component_html += utils.add_embed(component['url'])
    elif component_type == 'html-embed' and component['content'].startswith('<iframe'):
        m = re.search(r'src="?(http[^"\s]+)"?', component['content'])
        if m:
            component_html = utils.add_embed(m.group(1))
        else:
            logger.warning('unhandled html-embed iframe src in ' + component['_ref'])
    elif component_type == 'map' and component['provider'] == 'mapbox':
        caption = component['name']
        img_src = config.server + '/map?latitude=' + str(component['latitude']) + '&longitude=' + str(component['longitude']) + '&zoom=' + str(component['zoomLevel'])
        if component.get('markers'):
            legend = []
            colors = ["Red", "Orange", "Gold", "Green", "Blue", "Indigo", "Violet"]
            for i, marker in enumerate(component['markers']):
                marker['color'] = colors[i]
                legend.append('<span style="color:' + colors[i] + ';">● ' + marker['label'] + '</span>')
            img_src += '&markers=' + quote_plus(json.dumps(component['markers'], separators=(',', ':')))
            caption += ' | Legend: ' + ', '.join(legend)
        component_html += utils.add_image(img_src, caption)
    elif component_type == 'accordion':
        for it in component['items']:
            component_html += '<details style="margin:1em 0 1em 1em; padding:1em; border:1px solid light-dark(#333,#ccc); border-radius:10px;"><summary><b>' + it['title'] + '</b></summary>'
            for content in it['content']:
                component_html += format_component(content)
            component_html += '</details>'
    elif component_type == 'product-quick-picks':
        if component.get('headline'):
            component_html += '<h3>' + component['headline'] + '</h3>'
        component_html += '<ul>' + component['text'].replace('<p>', '<li>').replace('</p>', '</li>') + '</ul>'
    elif component_type == 'product-offer-card-container':
        if component['title']:
            component_html += '<h3>' + component['title'] + '</h3>'
        component_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
        for it in component['productOfferCards']:
            component_html += '<div style="flex:1; min-width:256px;">' + format_component(it) + '</div>'
        component_html += '</div>'
    elif component_type == 'product-offer-card':
        if component['hideProduct'] == False:
            # print(component['_ref'])
            component_html += '<div style="margin:1em 0; padding:1em; border:1px solid light-dark(#333,#ccc); border-radius:10px;">'
            if component.get('sticker'):
                component_html += '<div style="background-color:#e2f380; width:max-content; padding:8px; transform:skew(-15deg); font-weight:bold;">' + component['sticker'] + '</div>'
            component_html += '<div style="font-size:larger;"><a href="' + component['mainLink'] + '" target="_blank"><b>' + component['title'] + '</b></a></div>'
            if component.get('subtitle'):
                component_html += '<div><b>' + component['subtitle'] + '</b></div>'
            component_html += '<div style="display:flex; flex-wrap:wrap; gap:1em; margin-top:8px;">'
            if component.get('images') and component['images'][0].get('url'):
                component_html += '<div style="flex:1; min-width:240px;"><img src="' + resize_image(component['images'][0]['url'], 640, '3x2') + '" style="width:100%;"></div>'
            elif component['product'].get('images') and component['product']['images'][0].get('url'):
                component_html += '<div style="flex:1; min-width:240px;"><img src="' + resize_image(component['product']['images'][0]['url'], 640, '3x2') + '" style="width:100%;"></div>'
            component_html += '<div style="flex:1; min-width:240px;">' + component['description']
            if component['shouldDisplayReviewLink'] == True and component.get('reviewLink'):
                component_html += '<p><a href="' + component['reviewLink'] + '" target="_blank">Read our review</a></p>'
            # for it in component['offers']['manualOffers']:
            for it in component['offersToDisplay']:
                if it.get('url'):
                    caption = ''
                    if it.get('price'):
                        caption = it['price']
                        if it.get('originalPrice'):
                            caption = '<s>' + it['originalPrice'] + '</s> ' + caption
                    elif it.get('originalPrice'):
                        caption = it['originalPrice']
                    if not caption:
                        caption = 'Buy'
                    caption +=  ' at ' + it['merchantText']
                    component_html += utils.add_button(it['merchantLink'], caption, button_color='#6a29d5')
            component_html += '</div></div></div>'
    elif component_type == 'live-story-post':
        dt = dateutil.parser.parse(component['__fields']['created_at'])
        component_html += '<div style="font-size:smaller;">' + utils.format_display_date(dt)
        if component['__fields']['updated_at'] != component['__fields']['created_at']:
            dt = dateutil.parser.parse(component['__fields']['updated_at'])
            component_html += ' (updated ' + utils.format_display_date(dt) + ')'
        component_html += '</div>'
        component_html += '<div style="font-size:larger; padding:8px 0;"><a href="' + component['socialShare']['canonicalUrl'] + '" target="_blank"><b>' + component['headline'] + '</b></a></div>'
        if component.get('byline'):
            component_html += '<div>' + component['byline'] + '</div>'
        for content in component['content']:
            component_html += format_component(content)
    elif component_type == 'divider':
        if component['componentVariation'] == 'divider_short':
            component_html += '<hr style="width:72px; margin:1em 0; border-top:5px solid #6e6e6e;">'
        else:
            component_html += '<hr style="margin:1em 0; border-top:5px solid #6e6e6e;">'
    elif component_type == 'footnote':
        component_html = '<p style="font-size:smaller; filter:brightness(80%);">' + component['text'] + '</p>'
    elif component_type == 'editor-note':
        if not re.search(r'sign up for|look-of-the-week', component['text'], flags=re.I):
            component_html = '<div style="margin:1em 0; padding:1em; border:1px solid light-dark(#333,#ccc); border-radius:10px; font-size:smaller; filter:brightness(80%);">' + component['text'] + '</div>'
    elif component_type == 'correction':
        component_html = '<p style="font-size:smaller; filter:brightness(80%);">'
        if component.get('prefix'):
            component_html += component['prefix'].upper() + ': '
        component_html += component['text'] + '</p>'
    elif component_type == 'disclaimer':
        component_html = '<div style="font-size:smaller; filter:brightness(80%);">' + component['text'] + '</div>'
    elif component_type == 'factbox':
        if component['slug'] != 'get-5-things-in-your-inbox':
            component_html = '<div style="margin:1em 0; padding:1em; border:1px solid light-dark(#333,#ccc); border-radius:10px;">'
            if component.get('title'):
                component_html += '<div style="font-weight:bold; text-transform:uppercase;">' + component['title'] + '</div>'
            component_html += '<ul style="font-size:smaller;">'
            for it in component['items']:
                component_html += '<li>' + it['text'] + '</li>'
            component_html += '</ul></div>'
    elif component_type == 'related-content' or component_type == 'commerce-promo-widget' or component_type == 'action-bar':
        pass
    else:
        logger.warning('unhandled component ' + component['_ref'])
    return component_html


def get_cms_content(url, data_uri, client_id, deployment_key, save_debug=False):
    if not data_uri or not client_id or not deployment_key:
        r = curl_cffi.get(url, impersonate="chrome", proxies=config.proxies, verify=certifi.where())
        if not r or r.status_code != 200:
            logger.warning('error getting ' + url)
            return None
        page_html = r.text
        if save_debug:
            utils.write_file(page_html, './debug/debug.html')

        soup = BeautifulSoup(page_html, 'lxml')

        if not data_uri:
            if soup.html.get('data-uri'):
                data_uri = soup.html['data-uri']
            else:
                logger.warning('unknown data-uri for ' + url)
                return None

        if not client_id or not deployment_key:
            el = soup.find('script', string=re.compile(r'PRODUCT_FINDER_CONTENT_API_UDK'))
            if el:
                i = el.string.find('{')
                j = el.string.rfind('}') + 1
                window_env = json.loads(el.string[i:j])
            else:
                logger.warning('unable to find window.env data in ' + url)
                return None
            client_id = window_env['LIVESTORY_CLIENT_KEY_CONTENT_API']
            deployment_key = window_env['PRODUCT_FINDER_CONTENT_API_UDK']

    api_url = "https://content.api.cnn.com/api/v1/content/" + base64.b64encode(data_uri.replace('cms.cnn.com', '').encode()).decode() + "/renderer/json?cb=" + str(int(datetime.timestamp(datetime.now()) * 1000)) + "&rt=0"
    headers = {
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "x-clay-site": "cnn",
        "x-client-id": client_id,
        "x-unique-deployment-key": deployment_key
    }
    r = curl_cffi.get(api_url, headers=headers, impersonate="chrome", proxies=config.proxies, verify=certifi.where())
    if r.status_code != 200:
        return None

    cms_json = r.json()
    cms_json['client_id'] = client_id
    cms_json['deployment_key'] = deployment_key
    return cms_json


def get_content(url, args, site_json, save_debug=False):
    data_uri = ''
    if url.startswith('www.bleacherreport.com'):
        return breport.get_content(url, args, site_json, save_debug)
    elif url.startswith('cms.cnn.com'):
        data_uri = url
    else:
        split_url = urlsplit(url)
        paths = list(filter(None, split_url.path.strip('/').split('/')))
        if split_url.netloc == 'lite.cnn.com':
            url = url.replace('lite.cnn.com', 'www.cnn.com')
        elif split_url.netloc == 'ix.cnn.io':
            if 'charts' in paths:
                return datawrapper.get_content(url, args, site_json, save_debug)
            else:
                logger.warning('unhandled url ' + url)
                return None

    cms_json = get_cms_content(url, data_uri, args.get('client_id'), args.get('deployment_key'), save_debug)
    if not cms_json:
        return None

    if save_debug:
        utils.write_file(cms_json, './debug/debug.json')
    return get_item(cms_json, args, site_json, save_debug)


def get_item(cms_json, args, site_json, save_debug):
    page_type = cms_json['__meta']['pageType']
    main_json = cms_json['main'][0]
    config_json = main_json['configuration'][0]

    item = {}
    item['id'] = main_json['_ref']
    item['url'] = config_json['canonicalUrl']
    item['title'] = config_json['headline']

    dt = dateutil.parser.parse(config_json['__fields']['created_at'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = dateutil.parser.parse(config_json['__fields']['updated_at'])
    item['date_modified'] = dt.isoformat()

    authors = []
    if config_json.get('authors'):
        authors += [x for x in config_json['authors']]
    if config_json.get('editors'):
        authors += [x['text'] + ' (editor)' for x in config_json['editors'] if x['text'] not in authors]
    if config_json.get('producers'):
        authors += [x['text'] + ' (producer)' for x in config_json['producers'] if x['text'] not in authors]
    if len(authors) > 0:
        item['authors'] = [{"name": x} for x in authors]
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
        }

    item['tags'] = []
    if config_json.get('section'):
        item['tags'].append(config_json['section'])
    if config_json.get('subsection'):
        item['tags'].append(config_json['subsection'])
    if config_json.get('subsubsection'):
        item['tags'].append(config_json['subsubsection'])
    if config_json.get('tags'):
        for it in config_json['tags']:
            if it.get('tagNames'):
                item['tags'] += [x for x in it['tagNames'] if x not in item['tags']]
    if config_json.get('contentEnrichment') and config_json['contentEnrichment'].get('cep_tags'):
        item['tags'] += [x['label'] for x in config_json['contentEnrichment']['cep_tags'] if x['label'].lower() not in item['tags']]
    if len(item['tags']) == 0:
        del item['tags']

    if config_json.get('thumbnail'):
        item['image'] = resize_image(config_json['thumbnail'][0]['url'])
    elif config_json.get('metaImage'):
        item['image'] = resize_image(config_json['metaImage'][0]['url'])

    if config_json.get('metaDescription'):
        item['summary'] = config_json['metaDescription']

    item['content_html'] = ''
    if page_type == 'live-story':
        for component in cms_json['top']:
            if component['_ref'].startswith('cms.cnn.com/_components/live-story-lede'):
                item['content_html'] += format_component(component['items'][0])
                break

        item['content_html'] += '<div style="margin:1em 0; padding:1em; border:1px solid light-dark(#333,#ccc); border-radius:10px;">'
        for component in main_json['spotlight']:
            item['content_html'] += format_component(component)
        item['content_html'] += '</div>'

        posts = {
            "all": []
        }
        for i, component in enumerate(main_json['items']):
            if component.get('formattedFilterTags'):
                key = component['formattedFilterTags']
            else:
                key = 'all'
            if key not in posts:
                posts[key] = []
            post = format_component(component)
            posts['all'].append(post)
            if key != 'all':
                posts[key].append(post)
        for key, val in posts.items():
            if key != 'all':
                n = len(val)
                item['content_html'] += '<details style="margin:1em 0;"><summary style="font-size:larger; font-weight:bold; margin-bottom:1em;">' + key.title().replace('Cnn', 'CNN') + ' (' + str(n) + ' posts)</summary>' + '<hr style="margin:1em 0; border-top:5px solid #6e6e6e;">'.join(val) + '</details>'
            # if i > 0:
            #     item['content_html'] += '<hr style="margin:1em 0; border-top:5px solid #6e6e6e;">'
            # item['content_html'] += format_component(component)
        n = len(posts['all'])
        item['content_html'] += '<details style="margin:1em 0;"><summary style="font-size:larger; font-weight:bold; margin-bottom:1em;">All posts (' + str(n) + ' posts)</summary>' + '<hr style="margin:1em 0; border-top:5px solid #6e6e6e;">'.join(posts['all']) + '</details>'
    else:
        if main_json.get('lede'):
            for component in main_json['lede']:
                item['content_html'] += format_component(component)

        if main_json.get('content'):
            location = ''
            image_expandable = False
            for component in main_json['content']:
                component_html = ''
                component_type = urlsplit(component['_ref']).path.strip('/').split('/')[2]
                if component_type == 'source':
                    location = component['location']
                    continue
                elif page_type == 'gallery' and component_type == 'gallery-inline':
                    item['_gallery'] = get_gallery_images(component)
                    item['content_html'] += utils.add_gallery(item['_gallery'], gallery_url=config.server + '/gallery?url=' + quote_plus(item['url']))
                    continue
                elif component_type == 'image' and component['componentVariation'] == 'image_expandable':
                    if image_expandable == False:
                        item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:1em 0;">'
                        image_expandable = True
                    component_html += '<div style="flex:1; min-width:360px;">'
                elif image_expandable:
                    item['content_html'] += '</div>'
                    image_expandable = False
                component_html += format_component(component)
                if location:
                    component_html = re.sub(r'^<p>', '<p><b>' + location + '</b> &mdash; ', component_html, count=1)
                    location = ''
                elif image_expandable:
                    component_html += '</div>'
                item['content_html'] += component_html

        if (page_type == 'video' or page_type == 'vertical-video') and 'embed' not in args and 'summary' in item:
            item['content_html'] += '<p>' + item['summary'] + '</p>'

    return item


def get_feed(url, args, site_json, save_debug=False):
    cms_json = get_cms_content(url, '', '', '', save_debug)
    if not cms_json:
        return None
    if save_debug:
        utils.write_file(cms_json, './debug/cnn.json')

    n = 0
    feed = utils.init_jsonfeed(args)
    feed_items = []

    page_type = cms_json['__meta']['pageType']
    if page_type == 'section':
        for it in cms_json['head']:
            if 'componentVariation' in it and it['componentVariation'] == 'meta-title':
                feed['title'] = it['title']

        cards = []
        def find_cards(it):
            nonlocal cards
            if isinstance(it, dict):
                if it.get('cards'):
                    cards.extend(it['cards'])
                if it.get('items'):
                    for x in it['items']:
                        find_cards(x)
        for it in cms_json['main']:
            find_cards(it)
        if cards and save_debug:
            utils.write_file(cards, './debug/feed.json')

        urls = []
        for card in cards:
            if card['url'] in urls:
                continue
            urls.append(card['url'])
            if save_debug:
                logger.debug('getting content for ' + card['url'])
            if card.get('uri') and isinstance(card['uri'], str):
                card_json = get_cms_content('', card['uri'], cms_json['client_id'], cms_json['deployment_key'])
            else:
                card_json = get_cms_content(card['url'], '', cms_json['client_id'], cms_json['deployment_key'])
            if card_json:
                item = get_item(card_json, args, site_json, save_debug)
                if item:
                    if utils.filter_item(item, args) == True:
                        feed_items.append(item)
                        n += 1
                        if 'max' in args:
                            if n == int(args['max']):
                                break

    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed