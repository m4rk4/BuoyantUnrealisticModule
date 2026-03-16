import json, re, requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, unquote_plus, urlsplit

import config
from feedhandlers import rss
import utils

import logging

logger = logging.getLogger(__name__)


def get_full_image(img_src):
    m = re.search(r'(https:\/\/s\.yimg\.com\/os\/creatr-uploaded-images\/[^\.]+)', img_src)
    if m:
        return m.group(1)
    m = re.search(r'image_uri=([^&]+)', img_src)
    if m:
        return unquote_plus(m.group(1))
    return img_src


def get_image(image_wrapper):
    img = image_wrapper.find('img')
    if not img:
        return ''
    if img.get('src'):
        img_src = img['src']
    elif img.get('data-src'):
        img_src = img['data-src']
    else:
        logger.warning('unknown img src in ' + str(img))
        return ''
    caption = ''
    if img.get('alt'):
        caption = img['alt']
    else:
        figcap = image_wrapper.find('figcaption')
        if figcap:
            caption = figcap.get_text()
    it = image_wrapper.find('a', class_='link')
    if it:
        link = it['href']
    else:
        link = ''
    return utils.add_image(get_full_image(img_src), caption, link=link)


def get_video(video_wrapper):
    yvideo = video_wrapper.find(class_='caas-yvideo')
    if not yvideo:
        return ''
    video_config = json.loads(yvideo['data-videoconfig'])
    if video_config.get('media_id_1'):
        video_id = video_config['media_id_1']
    elif video_config.get('playlist'):
        video_id = video_config['playlist']['mediaItems'][0]['id']
    else:
        logger.warning('unknown video id in ' + str(yvideo))
        return ''
    video_json = utils.get_url_json('https://video-api.yql.yahoo.com/v1/video/sapi/streams/{}?protocol=http&format=m3u8,mp4,webm&site=news'.format(video_id))
    if not video_json:
        return ''
    # utils.write_file(video_json, './debug/video.json')
    for video in video_json['query']['results']['mediaObj'][0]['streams']:
        if video['format'] == 'm3u8':
            break
    if video['format'] != 'm3u8':
        video = utils.closest_dict(video_json['query']['results']['mediaObj'][0]['streams'], 'height', 480)
        if not video:
            video = video_json['query']['results']['mediaObj'][0]['streams'][0]
    caption = []
    if video_json['query']['results']['mediaObj'][0]['meta'].get('title'):
        caption.append(video_json['query']['results']['mediaObj'][0]['meta']['title'])
    if video_json['query']['results']['mediaObj'][0]['meta'].get('attribution'):
        caption.append(video_json['query']['results']['mediaObj'][0]['meta']['attribution'])
    poster = video_json['query']['results']['mediaObj'][0]['meta']['thumbnail']
    return utils.add_video(video['host'] + video['path'], video['mime_type'], poster, ' | '.join(caption))


def get_iframe(iframe_wrapper):
    embed = iframe_wrapper.find('iframe')
    if not embed:
        embed = iframe_wrapper.find('blockquote')
    embed_src = ''
    if embed.get('src'):
        embed_src = embed['src']
    elif embed.get('data-src'):
        embed_src = embed['data-src']
    if not embed_src:
        return ''
    return utils.add_embed(embed_src)


def get_iframely(iframely_wrapper):
    el = iframely_wrapper.find(attrs={"data-iframely-url": True})
    if el:
        iframely_html = utils.get_url_html(el['data-iframely-url'])
        if iframely_html:
            iframely_soup = BeautifulSoup(iframely_html, 'lxml')
            it = iframely_soup.find('meta', attrs={"name": "canonical"})
            if it:
                return utils.add_embed(it['content'])
    return ''



def get_video_json(video_id, site, region='US'):
    api_url = 'https://video-api.yql.yahoo.com/v1/video/sapi/streams/' + video_id + '?protocol=http&format=m3u8,mp4,webm&region=' + region + '&site=' + site
    api_json = utils.get_url_json(api_url)
    if api_json:
        try:
            video_json = api_json['query']['results']['mediaObj'][0]
        except:
            video_json = None
    else:
        video_json = None
    return video_json


def format_atom(atom, products={}):
    atom_html = ''
    if atom['type'] == 'text' and atom['tagName'] == 'p':
        if re.search(r'(<strong>|<em>)(<strong>|<em>)?(Read more:|Related:)', atom['content'], flags=re.I) or re.search(r'data-ylk="[^"]*slk:(Click here|Read the latest)', atom['content']) or re.search(r'href="[^"]+people-news-daily-newsletter-sign-up', atom['content']):
            return ''
        atom_html += '<p>' + re.sub(r'\s?(class|data-i13n|data-ylk|rel)="[^"]+"', '', atom['content']) + '</p>'
    elif atom['type'] == 'heading':
        atom_html += '<{0}>{1}</{0}>'.format(atom['tagName'], atom['content'])
    elif atom['type'] == 'horizontalRule':
        atom_html += '<hr style="margin:2em 0;>'
    elif atom['type'] == 'list':
        atom_html += '<' + atom['tagName'] + '>'
        for it in atom['items']:
            list_item = ''
            for val in it['val']:
                list_item += format_atom(val, products)
            atom_html += '<li style="margin:0.5em 0;">' + re.sub(r'^<p>|</p>$', '', list_item) + '</li>'
        atom_html += '</' + atom['tagName'] + '>'
    elif atom['type'] == 'blockquote':
        quote = ''
        for it in atom['items']:
            for val in it['val']:
                quote += format_atom(val, products)
        atom_html += utils.add_blockquote(quote, False)
    elif atom['type'] == 'image':
        captions = []
        if atom.get('caption'):
            captions.append(re.sub(r'^<i>|</i>$', '', atom['caption']).replace('<br>', ' | '))
        if atom.get('credit'):
            captions.append(atom['credit'])
        atom_html += utils.add_image(atom['size']['resized']['url'], ' | '.join(captions), link=atom['size']['original']['url'])
    elif atom['type'] == 'core-slideshow':
        gallery_images = []
        for slide in atom['data']['slides']:
            gallery_images.append({
                "src": slide['size']['original']['url'],
                "thumb": slide['size']['resized']['url'],
                "caption": slide.get('caption')
            })
        atom_html += utils.add_gallery(gallery_images, gallery_caption=atom['data'].get('title'), show_gallery_link=False, show_gallery_poster=True)
    elif atom['type'] == 'yvideo':
        video_json = get_video_json(atom['config']['playlist']['mediaItems'][0]['id'], atom['config']['site'], atom['config']['region'])
        if video_json:
            atom_html += utils.add_video(video_json['streams'][0]['host'] + video_json['streams'][0]['path'], video_json['streams'][0]['mime_type'], video_json['meta']['thumbnail'], video_json['meta']['title'])
    elif atom['type'] == '3pvideo' and atom['subtype'] == 'youtube':
        atom_html += utils.add_embed(atom['url'])
    elif atom['type'] == 'iframe' or atom['type'] == 'youtube':
        atom_html += utils.add_embed(atom['url'])
    elif atom['type'] == 'tweet':
        atom_html += utils.add_embed('https://x.com/_/status/' + atom['id'])
    elif atom['type'] == 'instagram':
        link = ''
        for it in atom['items']:
            for val in it['val']:
                if val.get('content'):
                    for m in re.findall(r'href="([^"]+)', val['content']):
                        if atom['id'] in m:
                            link = m
                            break
                if link:
                    break
            if link:
                break
        if link:
            atom_html += utils.add_embed(link)
    elif atom['type'] == 'iframely':
        page_html = utils.get_url_html(atom['url'])
        if page_html:
            soup = BeautifulSoup(page_html, 'lxml')
            el = soup.find('meta', attrs={"name": "canonical"})
            if el:
                return utils.add_embed(el['content'])
    elif atom['type'] == 'core-commerce' and atom['id'] in products:
        product = products[atom['id']]
        if product['moduleStyle'] == 'large':
            atom_html += '<div style="width:100%; margin:1em 0; padding:0 0 1em 0; border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb;">'
            if product.get('image') and product['image'].get('url'):
                atom_html += '<img src="' + product['image']['url'] + '" style="width:100%; border-radius:10px 10px 0 0;" />'
            atom_html += '<h3 style="text-align:center; padding:0 1em;">' + product['productName'] + '</h3>'
            if product.get('editorialText') or product.get('rating'):
                atom_html += '<div style="display:flex; flex-wrap:wrap; margin:0 1em; gap:1em;">'
                if product.get('editorialText'):
                    atom_html += '<div style="flex:2; min-width:256px; margin:1em 0;">' + product['editorialText'] + '</div>'
                if product.get('rating'):
                    atom_html += '<div style="flex:1; min-width:180px; margin:1em 0;">' + utils.add_score_gauge(product['rating'], str(product['rating']), margin='0 auto') + '</div>'
                atom_html += '</div>'
            if product.get('pros') or product.get('cons'):
                atom_html += '<div style="display:flex; flex-wrap:wrap; margin:0 1em; gap:1em;">'
                if product.get('pros'):
                    atom_html += '<div style="flex:1; min-width:256px; margin:1em 0;"><div><b>Pros</b></div><ul>' + ''.join(['<li>' + x + '</li>' for x in product['pros']]) + '</ul></div>'
                if product.get('cons'):
                    atom_html += '<div style="flex:1; min-width:256px; margin:1em 0;"><div><b>Cons</b></div><ul>' + ''.join(['<li>' + x + '</li>' for x in product['cons']]) + '</ul></div>'
                atom_html += '</div>'
            if product.get('productOffers'):
                for offer in product['productOffers']:
                    params = parse_qs(urlsplit(offer['affiliateUrl']).query)
                    if params.get('gcReferrer'):
                        link = params['gcReferrer'][0]
                    else:
                        link = offer['affiliateUrl']
                    atom_html += utils.add_button(link, offer['ctaText'])
            atom_html += '</div>'
        elif product['moduleStyle'] == 'mini':
            offer = product['productOffers'][0]
            params = parse_qs(urlsplit(offer['affiliateUrl']).query)
            if params.get('gcReferrer'):
                link = params['gcReferrer'][0]
            else:
                link = offer['affiliateUrl']
            atom_html += '<div style="display:grid; grid-template-areas:\'image content\'; grid-template-columns:120px auto; grid-gap:0.5em; width:100%; align-items:center; font-size:smaller;">'
            atom_html += '<div style="grid-area:image; width:120px;";><img src="' + product['image']['url'] + '" style="width:100%;" /></div>'
            atom_html += '<div style="grid-area:content;"><div style="display:flex; flex-wrap:wrap; width:100%; align-items:center;">'
            atom_html += '<div style="flex:1; min-width:128px;"><p style="font-size:larger; font-weight:bold;"><a href="' + link + '" target="_blank" style="text-decoration:none;">' + product['productName'] + '</a></p><p>'
            if offer.get('formattedSalePrice'):
                atom_html += '<span style="font-weight:bold; color:red;">' + offer['formattedSalePrice'] + '</span>'
                if offer.get('formattedOriginalPrice'):
                    atom_html += ' <s>' + offer['formattedOriginalPrice'] + '</s>'
                if offer.get('formattedSavedPrice'):
                    atom_html += ' <span style="font-weight:bold;">Save ' + offer['formattedSavedPrice'] + '</span>'
            else:
                atom_html += '<span style="font-weight:bold;">' + offer['formattedOriginalPrice'] + '</span>'
            atom_html += '</p></div>'
            atom_html += '<div style="flex:1; min-width:128px;">' + utils.add_button(link, offer['ctaText']) + '</div>'
            atom_html += '</div></div></div>'
    elif atom['type'] == 'core-stock-ticker':
        if atom['attribs'].get('comparisons'):
            symbols = []
            symbols.append(atom['attribs']['symbol'])
            symbols += atom['attribs']['comparisons'].split(',')
            atom_html += utils.add_stock_chart_compare(symbols)
        else:
            atom_html += utils.add_stock_chart(atom['attribs']['symbol'])
    elif atom['type'] == 'core-liveblog':
        for it in atom['items']:
            for val in it['val']:
                atom_html += format_atom(val, products)
    elif atom['type'] == 'liveblogpost':
        if atom.get('authors'):
            byline = utils.format_byline([{"name": x['author']['displayName']} for x in atom['authors']])
        else:
            byline = ''
        if atom.get('lastModifiedTime'):
            dt = datetime.fromisoformat(atom['lastModifiedTime']['iso'])
        elif atom.get('pubDate'):
            dt = datetime.fromisoformat(atom['pubDate']['iso'])
        atom_html += '<div style="display:flex; align-items:end; gap:1em;"><div style="width:24px;"><span style="color:light-dark(#ccc,#333); font-size:48px;">●</span></div><div style="line-height:1.5em;"><b>' + utils.format_display_date(dt) + '</b><br/>' + byline + '</div></div>'
        atom_html += '<div style="margin-left:13px; border-left:2px solid light-dark(#ccc,#333); padding:1px 0 0 1em;"><h3>' + atom['headline'] + '</h3>'
        for it in atom['items']:
            for val in it['val']:
                atom_html += format_atom(val, products)
        atom_html += '</div>'
    else:
        logger.warning('unhandled atom type ' + atom['type'])
    return atom_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    if 'yahoo.com' in split_url.netloc:
        site = split_url.netloc.split('.')[0]
        if site == 'www':
            site = paths[0]
    elif split_url.netloc == 'sports.yahoo.com':
        site = 'sports'
    elif split_url.netloc == 'www.engadget.com':
        site = 'engadget'
    elif split_url.netloc == 'www.aol.com':
        site = 'aolhomepage'
    
    data_api_url = split_url.scheme + '://' + split_url.netloc + '/caas/content/article/dataApi?dd_resource=CaaS-SeamlessArticle&appid=commerce_web&lang=en-US&partner=none&region=US&site=' + site + '&url=' + quote_plus(split_url.scheme + '://' + split_url.netloc + split_url.path)
    data_api = utils.get_url_json(data_api_url, site_json=site_json)
    if data_api:
        if save_debug:
            utils.write_file(data_api, './debug/debug.json')
        try:
            content_meta = data_api['items'][0]['data']['contentMeta']
        except:
            logger.warning('not contentMeta data in ' + data_api_url)
            return None

        item = {}
        item['id'] = content_meta['contentI13n']['uuid']

        if content_meta['seoMeta'].get('canonicalUrl'):
            item['url'] = content_meta['seoMeta']['canonicalUrl']
        elif content_meta['seoMeta'].get('seamlessUrl'):
            item['url'] = content_meta['seoMeta']['seamlessUrl']
        elif content_meta['seoMeta'].get('previewLink'):
            item['url'] = content_meta['seoMeta']['previewLink']

        item['title'] = content_meta['seoMeta']['title']

        dt = datetime.fromisoformat(content_meta['dates']['publishDate']['iso'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        if content_meta['dates'].get('modifiedDate') and content_meta['dates']['modifiedDate'].get('iso'):
            dt = datetime.fromisoformat(content_meta['dates']['modifiedDate']['iso'])
            item['date_modified'] = dt.isoformat()

        item['authors'] = []
        if content_meta['attribution'].get('authors'):
            item['authors'] += [{"name": x['name']} for x in content_meta['attribution']['authors']]
            item['author'] = {
                "name": utils.format_byline(item['authors'])
            }

        item['tags'] = []
        if content_meta.get('categoryLabel'):
            item['tags'].append(content_meta['categoryLabel'])
        if content_meta.get('siteSections') and content_meta['siteSections'].get('sectionItems'):
            item['tags'] += [x['sectionName'] for x in content_meta['siteSections']['sectionItems']]
        if content_meta['contentTags'].get('normalizedTags') and content_meta['contentTags']['normalizedTags'].get('editorialTags'):
            item['tags'] += content_meta['contentTags']['normalizedTags']['editorialTags'].copy()
        if content_meta['contentTags'].get('stockTickers'):
            item['tags'] += [x['symbol'] for x in content_meta['contentTags']['stockTickers']]
        if content_meta['seoMeta'].get('keywords'):
            item['tags'] += [x.strip() for x in content_meta['seoMeta']['keywords'].split(',')]
        if len(item['tags']) > 0:
            item['tags'] = utils.dedupe_case_insensitive(item['tags'])
        else:
            del item['tags']

        if content_meta['contentSummaries'].get('summary'):
            item['summary'] = content_meta['contentSummaries']['summary']

        item['content_html'] = ''    
        if content_meta['seoMeta'].get('subheadline'):
            item['content_html'] += '<p><em>' + content_meta['seoMeta']['subheadline'] + '</em></p>'

        if content_meta['contentImages'].get('shareImage') and content_meta['contentImages']['shareImage'].get('url'):
            item['image'] = content_meta['contentImages']['shareImage']['url']

        if content_meta.get('commerce') and content_meta['commerce'].get('products'):
            products = content_meta['commerce']['products']
        else:
            products = {}

        if content_meta['contentCover'].get('cover') and content_meta['contentCover']['cover'].get('type'):
            if 'image' not in item:
                if content_meta['contentCover']['cover']['type'] == 'image':
                    item['image'] = content_meta['contentCover']['cover']['size']['resized']['url']
                elif content_meta['contentCover']['cover']['type'] == 'yvideo':
                    if content_meta['contentCover']['cover']['config']['thumbnail']['size']['raw']:
                        item['image'] = content_meta['contentCover']['cover']['config']['thumbnail']['size']['raw']['url']
                    else:
                        item['image'] = content_meta['contentCover']['cover']['thumbnailUrl']
            if content_meta['contentCover']['enableLead'] == 'ON' or (content_meta['contentCover']['enableLead'] == 'DEFAULT' and (content_meta['storyAtoms'][0]['type'] != 'image' or content_meta['storyAtoms'][0]['type'] != 'yvideo')):
                item['content_html'] += format_atom(content_meta['contentCover']['cover'], products)

        if content_meta['contentSummaries'].get('aiSummary'):
            item['content_html'] += '<div style="width:100%; margin:1em 0; padding:0 1em; border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb;"><p><b>AI Summary</b></p><ul>'
            for it in content_meta['contentSummaries']['aiSummary']:
                if it['type'] == 'text':
                    item['content_html'] += '<li style="margin:0.5em 0;">' + it['value'] + '</li>'
            item['content_html'] += '</ul></div>'

        if content_meta['contentTags'].get('stockTickers'):
            item['content_html'] += '<p><b>In this article:</b></p><ul>'
            for it in content_meta['contentTags']['stockTickers']:
                item['content_html'] += '<li style="margin:0.5em 0;">' + utils.get_stock_price(it['symbol'], '', True) + '</li>'
            item['content_html'] += '</ul>'

        # TODO: first paragraph dropcap?
        for atom in content_meta['storyAtoms']:
            item['content_html'] += format_atom(atom, products)

        if content_meta['seoMeta'].get('providerContentUrl'):
            if urlsplit(content_meta['seoMeta']['providerContentUrl']).netloc != split_url.netloc:
                item['content_html'] += '<p><em>This article was originally published by <a href="' + content_meta['seoMeta']['providerContentUrl'] + '" target="_blank">' + content_meta['attribution']['providerBrand']['displayName'] + '</a>.</em</p>'
        return item

    clean_url = utils.clean_url(url)
    for i in range(3):
        # Need to load the article page first to set appropriate cookies otherwise some embedded content is restricted
        # Sometimes need to do this multiple times
        s = utils.requests_retry_session()
        headers = config.default_headers
        s.headers.update(headers)
        r = s.get(url, headers=headers)
        if r.status_code != 200:
            return None
        cookies = []
        c = s.cookies.get_dict()
        for key, val in c.items():
            cookies.append('{}={}'.format(key, val))
        headers['cookie'] = '; '.join(cookies)
        article_html = r.text
        caas_json = None
        if 'www.autoblog.com' not in url:
            caas_url = 'https://www.yahoo.com/caas/content/article/?url=' + quote_plus(clean_url)
            caas_json = utils.get_url_json(caas_url, headers=headers)
        if not caas_json:
            m = re.search(r'"pstaid":"([^"]+)"', article_html)
            if not m:
                m = re.search(r'pstaid:\s*\'([^\']+)\'', article_html)
                if not m:
                    m = re.search(r'data-post-uuid="([^"]+)"', article_html)
                    if not m:
                        logger.warning('unable to find post-id in ' + url)
                        return None
            caas_url = 'https://www.yahoo.com/caas/content/article/?uuid=' + m.group(1)
            caas_json = utils.get_url_json(caas_url, headers=headers)
            if not caas_json:
                return None
        # utils.write_file(caas_json, './debug/debug.json')
        if caas_json.get('redirectRequestUUID'):
            caas_url = 'https://www.yahoo.com/caas/content/article/?uuid=' + caas_json['redirectRequestUUID']
            caas_json = utils.get_url_json(caas_url, headers=headers)
            if not caas_json:
                return None
        if not re.search(r'caas-3p-blocked', caas_json['items'][0]['markup']):
            break

    if save_debug:
        utils.write_file(article_html, './debug/debug.html')
        utils.write_file(caas_json, './debug/debug.json')

    if re.search(r'caas-3p-blocked', caas_json['items'][0]['markup']):
        logger.warning('caas-3p-blocked content in ' + url)

    article_json = caas_json['items'][0]['schema']['default']
    data_json = caas_json['items'][0]['data']['partnerData']

    item = {}
    item['id'] = data_json['uuid']

    if data_json.get('canonicalUrl'):
        item['url'] = data_json['canonicalUrl']
    elif data_json.get('hrefLangs'):
        link = next((it for it in data_json['hrefLangs'] if it['rel'] == 'canonical'), None)
        if link:
            item['url'] = link['href']
    if not item.get('url'):
        if article_json.get('mainEntityOfPage'):
            item['url'] = article_json['mainEntityOfPage']
        elif data_json.get('url'):
            item['url'] = data_json['url']
        else:
            item['url'] = url

    item['title'] = article_json['headline']

    dt = datetime.fromisoformat(article_json['datePublished'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['dateModified'])
    item['date_modified'] = dt.isoformat()

    item['author'] = {
        "name": article_json['author']['name']
    }
    if data_json.get('providerBrand') and data_json['providerBrand'].get('displayName') and data_json['providerBrand']['displayName'] not in item['author']['name'] and data_json['providerBrand']['brandId'] not in item['url']:
        item['author']['name'] += ' ({})'.format(data_json['providerBrand']['displayName'])
    item['authors'] = []
    item['authors'].append(item['author'])

    item['tags'] = article_json['keywords'].copy()

    item['image'] = article_json['image']['url']

    item['summary'] = article_json['description']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    caas_soup = BeautifulSoup(caas_json['items'][0]['markup'], 'html.parser')
    caas_body = caas_soup.find(class_='caas-body')
    if save_debug:
        utils.write_file(str(caas_body), './debug/debug.html')

    for el in caas_body.find_all(class_='caas-curated-links'):
        el.decompose()

    for el in caas_body.select('p:has(> span.sailthru-signup-widget-close)'):
        for it in el.find_next_siblings():
            if (it.name == 'p' or it.name == 'h1') and re.search(r'thanks for signing up|watch for us in your inbox|subscribe now|daily digest', it.get_text(), flags=re.I):
                it.decompose()
            else:
                break
        el.decompose()

    for el in caas_body.find_all('figure'):
        new_html = get_image(el)
        if new_html:
            if re.search(r'https://www\.autoblog\.com/cars-for-sale/', new_html):
                # Ad
                el.decompose()
            else:
                el.insert_after(BeautifulSoup(new_html, 'html.parser'))
                el.decompose()

    for el in caas_body.find_all(class_='caas-carousel'):
        new_html = ''
        for slide in el.find_all(class_='caas-carousel-slide'):
            new_html += get_image(slide)
        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

    for el in caas_body.find_all(class_='caas-yvideo-wrapper'):
        new_html = get_video(el)
        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

    for el in caas_body.find_all(class_='caas-iframely'):
        new_html = get_iframely(el)
        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

    for el in caas_body.find_all(class_='caas-iframe-wrapper'):
        new_html = get_iframe(el)
        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

    for el in caas_body.find_all(class_='caas-iframe'):
        new_html = get_iframe(el)
        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

    for el in caas_body.find_all(class_='caas-pull-quote-wrapper'):
        logger.debug('caas-pull-quote-wrapper in ' + url)
        quote = ''
        for it in el.find_all('p'):
            if quote:
                quote += '<br/><br/>'
            quote += it.decode_contents()
        if re.search(r'^["“].*["”]$', quote) and len(re.findall(r'["“"”]', quote)) == 2:
            new_html = utils.add_pullquote(quote[1:-1])
        else:
            new_html = utils.add_blockquote(quote)
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

    for el in caas_body.find_all(class_='twitter-tweet-wrapper'):
        tweet_urls = el.find_all('a')
        new_html = utils.add_embed(tweet_urls[-1]['href'])
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

    for el in caas_body.find_all(class_='instagram-media-wrapper'):
        if el.blockquote and el.blockquote.get('data-instgrm-permalink'):
            new_html = utils.add_embed(el.blockquote['data-instgrm-permalink'])
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()
        else:
            logger.warning('unhandled instagram-media-wrapper in ' + url)

    for el in caas_body.find_all(class_=['pd-list', 'mini-pd']):
        if 'quick-overview' in el['class']:
            el.decompose()
            continue
        new_html = ''
        it = el.find(class_='overview-label')
        if it:
            new_html += '<h3>{}</h3>'.format(it.get_text().strip())
        for it in el.find_all(class_='list-item'):
            new_html = '<div style="width:90%; margin:auto; padding:8px; border:1px solid black; border-radius:10px;"><div style="display:flex; flex-wrap:wrap; gap:1em;">'
            info = el.find(class_=['edit-label', 'editor-label'])
            if info:
                new_html += '<div style="flex:0 0 100%;"><span style="color:#9a58b5;; font-weight:bold;">{}</span></div>'.format(info.get_text().strip())
            info = it.find(class_='img-container')
            if info:
                img = info.find('img')
                if img:
                    img_src = ''
                    if img.get('data-src'):
                        img_src = img['data-src']
                    elif img.get('src'):
                        img_src = img['src']
                    if img_src:
                        if info.a:
                            new_html += '<div style="flex:1; min-width:256px; margin:auto;"><a href="{}"><img src="{}" style="width:100%" /></a></div>'.format(utils.get_redirect_url(info.a['href']), img_src)
                        else:
                            new_html += '<div style="flex:1; min-width:256px; margin:auto;"><img src="{}" style="width:100%" /></div>'.format(img_src)
            new_html += '<div style="flex:2; min-width:256px; margin:auto;">'
            info = it.find(class_=['list-info', 'info-data'])
            if info:
                info_name = info.find(class_='product-name')
                if info_name:
                    if info_name.a:
                        new_html += '<div><a href="{}"><span style="font-size:1.2em; font-weight:bold">{}</span></a></div>'.format(utils.get_redirect_url(info_name.a['href']), info_name.get_text())
                    else:
                        new_html += '<div><span style="font-size:1.2em; font-weight:bold">{}</span></div>'.format(info_name.get_text())
            sib = it.find_next_sibling()
            if sib and sib.get('class') and 'bottom-info' in sib['class']:
                info = sib.find(class_='desc')
                if info:
                    new_html += '<p><small>{}</small></p>'.format(info.get_text())
                for info in sib.find_all(class_='cta-btn'):
                    new_html += '<div style="margin-top:0.8em; margin-bottom:0.8em; text-align:center;"><a href="{}"><span style="display:inline-block; min-width:8em; color:white; background-color:#9a58b5; padding:0.5em;">{}</span></a></div>'.format(utils.get_redirect_url(info['href']), info.get_text())
            else:
                info = it.find(class_='desc')
                if info:
                    new_html += '<p><small>{}</small></p>'.format(info.get_text())
                for info in it.find_all(class_='cta-btn'):
                    new_html += '<div style="margin-top:0.8em; margin-bottom:0.8em; text-align:center;"><a href="{}"><span style="display:inline-block; min-width:8em; color:white; background-color:#9a58b5; padding:0.5em;">{}</span></a></div>'.format(utils.get_redirect_url(info['href']), info.get_text())
            new_html += '</div></div>'
            if it.find(class_='commerce-score'):
                new_html += '<div style="font-weight:bold; text-align:center; padding-bottom:8px;">'
                score = it.find(class_='commerce-score-val')
                if score:
                    new_html += '<span style="font-size:2em; line-height:1em; vertical-align:middle;">{}</span>'.format(
                        score.get_text())
                score = it.find(class_='commerce-score-total')
                if score:
                    new_html += ' / ' + score.get_text()
                score = it.find(class_='commerce-score-text')
                if score:
                    new_html += ' ({})'.format(score.get_text())
                new_html += '</div>'
            info = el.find(class_='pros-cons')
            if info:
                new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                for ul in info.find_all('ul'):
                    new_html += '<div style="flex:1; min-width:256px;"><div style="font-size:1.1em; font-weight:bold;">{}</div>{}</div>'.format(ul.find_previous_sibling(class_='title').get_text(), str(ul))
                new_html += '</div>'
            new_html += '</div><div>&nbsp;</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    gallery_html = ''
    for el in caas_body.find_all('a', attrs={"data-ylk": re.compile(r'Full Image Gallery', flags=re.I)}):
        page_html = utils.get_url_html(el['href'])
        if page_html:
            gallery_soup = BeautifulSoup(page_html, 'lxml')
            gallery_html += '<h2><a href="{}">{}</a></h2>'.format(el['href'], gallery_soup.title.get_text())
            for slide in gallery_soup.find_all(class_='splide__slide'):
                if 'splide__default__slide' in slide['class'] or 'splide__thumbnail' in slide['class']:
                    continue
                img = slide.find('img')
                if img:
                    if img.get('data-splide-lazy'):
                        img_src = img['data-splide-lazy']
                    else:
                        img_src = img['src']
                    captions = []
                    it = slide.find(class_='splide__slide__content')
                    if it:
                        for li in it.find_all('li'):
                            captions.append(li.get_text())
                    gallery_html += utils.add_image(img_src, ' | '.join(captions))
            for it in caas_body.find_all('a', href=el['href']):
                if not it.get_text() and not it.find_parent('figure'):
                    parent = it.find_parent('p')
                    if parent:
                        parent.decompose()
            parent = el.find_parent('p')
            if parent:
                parent.decompose()

    for el in caas_body.find_all('ul', class_='caas-list-bullet'):
        it = el.find_previous_sibling()
        if it and re.search(r'Related\.\.\.|You Might Also Like|Most Read from', it.get_text()):
            it.decompose()
            el.decompose()

    for el in caas_body.find_all('a'):
        href = el.get('href')
        if href:
            if el.get('target'):
                el.attrs = {}
                el['target'] = '_blank'
            else:
                el.attrs = {}
            if href.startswith('https://shopping.yahoo.com/'):
                el['href'] = utils.get_redirect_url(href)
            else:
                el['href'] = href

    for el in caas_body.find_all(class_='caas-readmore'):
        i = 0
        sibs = el.find_next_siblings()
        while sibs[i:] and len(sibs[i:]) >= 3 and sibs[i].name == 'h2' and sibs[i+1].name == 'figure' and sibs[i+2].name == 'p':
            sibs[i].decompose()
            sibs[i + 1].decompose()
            sibs[i + 2].decompose()
            i += 3
        el.decompose()

    for el in caas_body.find_all('p', string=re.compile(r'^Read More:')):
        el.decompose()

    article_soup = BeautifulSoup(article_html, 'lxml')
    content_html = ''
    el = caas_soup.find(class_='caas-subheadline')
    if el:
        content_html += '<p><em>{}</em></p>'.format(el.get_text().strip())
    else:
        el = article_soup.find('h2', class_='subheadline')
        if el:
            content_html += '<p><em>{}</em></p>'.format(el.get_text().strip())

    el = caas_soup.find(class_=re.compile(r'caas-cover|caas-hero'))
    if el:
        if 'caas-figure' in el['class']:
            content_html += get_image(el)
        elif 'caas-carousel' in el['class']:
            # Slideshow - add lead image and remaining slides to end
            gallery_images = []
            gallery_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
            for i, slide in enumerate(el.find_all(class_='caas-carousel-slide')):
                new_html = get_image(slide)
                if new_html:
                    if i == 0:
                        content_html += new_html
                    gallery_html += '<div style="flex:1; min-width:360px;">' + new_html + '</div>'
                    m = re.search(r'src="([^"]+)"', new_html)
                    img_src = m.group(1)
                    m = re.search(r'<figcaption><small>(.*?)</small>', new_html)
                    if m:
                        caption = m.group(1)
                    else:
                        caption = ''
                    gallery_images.append({"src": img_src, "caption": caption, "thumb": img_src})
            if i % 2 == 0:
                gallery_html += '<div style="flex:1; min-width:360px;">&nbsp;</div>'
            gallery_html += '</div>'
            gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
            content_html += '<div><small><a href="{}" target="_blank">View photo gallery</a></small></div><div>&nbsp;</div>'.format(gallery_url)
            gallery_html = '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + gallery_html
        elif 'yvideo' in el['class']:
            content_html += get_video(el)
        elif 'caas-iframe' in el['class']:
            content_html += get_iframe(el)
        else:
            logger.debug('unhandled caas-cover element type with classes {}'.format(str(el['class'])))

    el = article_soup.find(attrs={"data-component": "ProsCons"})
    if el:
        for it in el.find_all('div', recursive=False):
            if it.find('ul'):
                content_html += '<h3>{}</h3><ul>'.format(it.h2.get_text())
                for li in it.find_all('li'):
                    content_html += '<li>{}</li>'.format(li.get_text())
                content_html += '</ul>'

    el = article_soup.find(attrs={"data-component": "ProductScores"})
    if el:
        for it in el.find_all('div'):
            score = it.get_text().strip()
            if score.isnumeric():
                content_html += '<h3>Review score: {}</h3>'.format(score)
                break

    for el in article_soup.find_all('ul', class_='vital-stats-list'):
        new_html = '<table>'
        for li in el.find_all('li'):
            it = li.find(class_='stat-title')
            if it:
                title = it.decode_contents()
            else:
                title = ''
            it = li.find(class_='vital-val')
            if it:
                val = it.decode_contents()
            else:
                val = ''
            new_html += '<tr><td>{}</td><td>{}</td></tr>'.format(title, val)
        new_html += '</table>'
        if caas_body.contents[0].name == 'figure':
            caas_body.contents[0].insert_after(BeautifulSoup(new_html, 'html.parser'))
        else:
            content_html += new_html

    content_html += caas_body.decode_contents() + gallery_html
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', content_html)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
