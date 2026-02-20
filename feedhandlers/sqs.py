import json, pytz, re
from bs4 import BeautifulSoup, NavigableString
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1080):
    if width < 0:
        return utils.clean_url(img_src)
    return utils.clean_url(img_src) + '?format={}w'.format(width)


def get_image(block, width=1080):
    image = {}
    el = block.find('img', attrs={"data-src": True})
    if el:
        image['src'] = el['data-src']
    else:
        el = block.find('img', attrs={"data-image": True})
        if el:
            image['src'] = el['data-image']
        else:
            el = block.find('img', attrs={"srcset": True})
            if el:
                image['src'] = utils.image_from_srcset(el['srcset'], width)
            else:
                el = block.find('img', attrs={"src": True})
                if el:
                    image['src'] = el['src']
    if 'src' in image:
        image['src'] = resize_image(image['src'], width)
        image['thumb'] = resize_image(image['src'], 640)
        el = block.find(class_='image-caption')
        if el:
            if el.p:
                image['caption'] = el.p.decode_contents()
            else:
                image['caption'] = el.decode_contents()
        else:
            image['caption'] = ''
        el = block.find('a', class_='sqs-block-image-link')
        if el:
            image['link'] = el['href']
    return image    


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    page_json = utils.get_url_json(split_url.scheme + '://' + split_url.netloc + split_url.path + '?format=json-pretty')
    if not page_json:
        return None
    if save_debug:
        utils.write_file(page_json, './debug/debug.json')

    if 'item' in page_json:
        post_json = page_json['item']
    elif 'collection' in page_json:
        post_json = page_json['collection']
    else:
        logger.warning('unknown post data in ' + url)
        return None

    item = {}
    item['id'] = post_json['id']
    item['url'] = split_url.scheme + '://' + split_url.netloc + post_json['fullUrl']
    item['title'] = post_json['title']

    # TODO: check timezone
    tz_loc = pytz.timezone('US/Eastern')
    if post_json.get('publishOn'):
        dt_loc = datetime.fromtimestamp(post_json['publishOn']/1000)
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
    if post_json.get('updatedOn'):
        dt_loc = datetime.fromtimestamp(post_json['updatedOn']/1000)
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        if 'date_published' not in item:
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)
        else:
            item['date_modified'] = dt.isoformat()

    if post_json.get('author'):
        item['author'] = {
            "name": post_json['author']['displayName']
        }
        item['authors'] = []
        item['authors'].append(item['author'])
    elif page_json.get('website'):
        item['author'] = {
            "name": page_json['website']['siteTitle']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

    item['tags'] = []
    if post_json.get('categories'):
        item['tags'] += post_json['categories']
    if post_json.get('tags'):
        item['tags'] += post_json['tags']
    if len(item['tags']) == 0:
        del item['tags']

    if post_json.get('assetUrl'):
        if post_json['assetUrl'].endswith('/'):
            item['image'] = utils.get_redirect_url(post_json['assetUrl'])
            if 'no-image' in item['image']:
                del item['image']
        else:
            item['image'] = post_json['assetUrl']
    elif post_json.get('seoData') and post_json['seoData'].get('seoImage'):
        item['image'] = post_json['seoData']['seoImage']['assetUrl']

    if post_json.get('excerpt'):
        soup = BeautifulSoup(post_json['excerpt'], 'html.parser')
        item['summary'] = soup.get_text()
    elif post_json.get('seoData') and post_json['seoData'].get('seoDescription'):
        item['summary'] = post_json['seoData']['seoDescription']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    item['content_html'] = ''

    if post_json.get('promotedBlock'):
        soup = BeautifulSoup(post_json['promotedBlock'] + post_json['body'], 'html.parser')
    elif post_json.get('body'):
        soup = BeautifulSoup(post_json['body'], 'html.parser')
    elif page_json.get('mainContent'):
        soup = BeautifulSoup(page_json['mainContent'], 'html.parser')

    # Remove beginning layout elements
    while not isinstance(soup.contents[0], NavigableString) and soup.contents[0].get('class') and list(set(['sqs-layout', 'row', 'col']) & set(soup.contents[0]['class'])):
        soup.contents[0].unwrap()

    if save_debug:
        utils.write_file(str(soup), './debug/debug.html')

    if site_json and site_json.get('decompose'):
        for it in site_json['decompose']:
            for el in utils.get_soup_elements(it, soup):
                el.decompose()

    if site_json and site_json.get('unwrap'):
        for it in site_json['unwrap']:
            for el in utils.get_soup_elements(it, soup):
                el.unwrap()

    if site_json and site_json.get('rename'):
        for it in site_json['rename']:
            for el in utils.get_soup_elements(it, soup):
                el.name = it['name']

    for el in soup.find_all(['h2', 'h3', 'h4', 'p', 'ol', 'ul']):
        el.attrs = {}

    for el in soup.find_all('blockquote', class_=False):
        el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

    blocks = soup.find_all('div', class_='sqs-block')
    if 'image' in item and 'sqs-block-image' not in blocks[0]['class'] and 'sqs-block-video' not in blocks[0]['class'] and 'sqs-block-embed' not in blocks[0]['class'] and 'skip_lede_img' not in args:
        item['content_html'] += utils.add_image(item['image'])

    for block in blocks:
        if not block.name:
            continue

        if 'sqs-block-html' in block['class'] or 'sqs-block-markdown' in block['class']:
            el = block.find(string=re.compile(r'^By ' + item['author']['name'], flags=re.I))
            if el:
                el.decompose()
            else:
                el = block.find('div', class_='sqs-html-content')
                if el:
                    item['content_html'] += el.decode_contents()
                else:
                    el = block.find('div', class_='sqs-block-content')
                    if el:
                        item['content_html'] += el.decode_contents()

        elif 'sqs-block-image' in block['class']:
            if block.find(class_='sqs-empty'):
                continue
            el = block.find_parent(class_='sqs-row')
            if el:
                gallery_images = []
                for it in el.find_all(class_='sqs-block-image'):
                    image = get_image(it, width=-1)
                    if 'src' in image:
                        gallery_images.append(image)
                    else:
                        logger.warning('unhandled sqs-block-image in ' + item['url'])
                    it.decompose()
                item['content_html'] += utils.add_gallery(gallery_images)
            else:
                image = get_image(block)
                if 'src' in image:
                    item['content_html'] += utils.add_image(image['src'], image.get('caption'), link=image.get('link'))
                else:
                    logger.warning('unhandled sqs-block-image in ' + item['url'])
            el = block.find(class_='image-card')
            if el:
                card_html = ''
                it = el.find(class_='image-title')
                if it:
                    card_html += '<h4>' + it.get_text(strip=True) + '</h4>'
                it = el.find(class_='image-subtitle')
                if it:
                    card_html += it.decode_contents()
                it = el.find(class_='image-button')
                if it:
                    if it.a:
                        card_html += '<a href="' + it.a['href'] + '">' + it.get_text(strip=True) + '</a>'
                item['content_html'] += utils.add_blockquote(card_html)

        elif 'sqs-block-gallery' in block['class']:
            # https://www.tokyocowboy.co/articles/uy1r8j003qdvb4ozr4qgplhd3yujyn
            # TODO: captions. Need and example.
            gallery_images = []
            el = block.find(class_='sqs-gallery')
            for it in el.find_all('noscript'):
                src = resize_image(it.img['src'], -1)
                thumb = resize_image(it.img['src'], 640)
                gallery_images.append({"src": src, "caption": '', "thumb": thumb})
            item['content_html'] += utils.add_gallery(gallery_images)

        elif 'sqs-block-video' in block['class']:
            if block.get('data-block-json'):
                data_json = json.loads(block['data-block-json'])
                # utils.write_file(data_json, './debug/video.json')
                if data_json.get('providerName'):
                    if data_json['providerName'] == 'YouTube' or data_json['providerName'] == 'Vimeo':
                        item['content_html'] += utils.add_embed(data_json['url'])
                    else:
                        logger.warning('unhandled video provider {} in {}'.format(data_json['providerName'], item['url']))
                else:
                    el = block.find(class_='sqs-native-video', attrs={"data-config-video": True})
                    if el:
                        data_json = json.loads(el['data-config-video'])
                        utils.write_file(data_json, './debug/video.json')
                        if data_json.get('alexandriaUrl'):
                            item['content_html'] += utils.add_video(data_json['alexandriaUrl'].replace('{variant}', 'playlist.m3u8'), 'application/x-mpegURL', data_json['alexandriaUrl'].replace('{variant}', 'thumbnail'))
                    else:
                        logger.warning('unhandled sqs-native-video ' + item['url'])
            else:
                logger.warning('unhandled sqs-block-video in ' + item['url'])

        elif 'sqs-block-embed' in block['class']:
            if block.get('data-block-json'):
                data_json = json.loads(block['data-block-json'])
                # print(data_json)
                if data_json.get('providerName') and data_json['providerName'] == 'Twitter':
                    item['content_html'] += utils.add_embed(data_json['url'])
                    continue
                elif data_json.get('html'):
                    if re.search(r'twitter-tweet', data_json['html'], flags=re.I):
                        m = re.findall(r'href="([^"]+)"', data_json['html'])
                        item['content_html'] += utils.add_embed(m[-1])
                        continue
                    elif re.search(r'instagram-media', data_json['html'], flags=re.I):
                        m = re.search(r'data-instgrm-permalink="([^"]+)"', data_json['html'])
                        item['content_html'] += utils.add_embed(m.group(1))
                        continue
                    elif re.search(r'iframe', data_json['html']):
                        # embed_soup = BeautifulSoup(data_json['html'], 'html.parser')
                        # it = embed_soup.find('iframe')
                        # item['content_html'] += utils.add_embed(it['src'])
                        m = re.search(r'<iframe[^>]+src="([^"]+)"', data_json['html'])
                        item['content_html'] += utils.add_embed(m.group(1))
                        continue
                    elif re.search(r'disqus', data_json['html'], flags=re.I):
                        continue
            logger.warning('unhandled sqs-block-embed in ' + item['url'])

        elif 'sqs-block-horizontalrule' in block['class']:
            item['content_html'] += '<hr/>'

        elif 'sqs-block-quote' in block['class']:
            quote = ''
            author = ''
            el = block.find('blockquote')
            if el:
                quote = re.sub(r'<span>(“|”)</span>', '', utils.bs_get_inner_html(el))
                it = block.find('figcaption', class_='source')
                if it:
                    author = re.sub(r'—\s*', '', it.get_text())
            if quote:
                item['content_html'] += utils.add_pullquote(quote, author)
            else:
                logger.warning('unhandled sqs-block-quote in ' + item['url'])

        elif 'sqs-block-code' in block['class']:
            if block.find(class_='adsbygoogle') or block.find(id=re.compile(r'taboola')) or block.find(class_='sidebar-widget-cta-container'):
                continue
            elif block.find('script', src=re.compile(r'apps.elfsight.com')):
                continue
            elif block.find('iframe'):
                it = block.find('iframe')
                if re.search(r'amazon-adsystem', it['src']):
                    continue
                else:
                    item['content_html'] += utils.add_embed(it['src'])
                    continue
            elif block.find('blockquote', class_='instagram-media'):
                it = block.find('blockquote', class_='instagram-media')
                item['content_html'] += utils.add_embed(it['data-instgrm-permalink'])
                continue
            elif block['data-block-type'] == "1337" and block.find('pre'):
                it = block.find('pre')
                it.attrs = {}
                it['style'] = 'margin:1em 0; padding:0.5em; white-space:pre; overflow-x:scroll; background-color:light-dark(#ccc,#333);'
                item['content_html'] += str(it)
                continue
            elif block['data-block-type'] == "23":
                el = block.find('a')
                if el:
                    it = el.find('img')
                    if it:
                        if it['src'].startswith('//'):
                            img_src = 'https:' + it['src']
                        else:
                            img_src = it['src']
                        img_src = utils.get_redirect_url(img_src)
                        img_src = re.sub(r'_SL\d+_', '_SL500_', img_src)
                        item['content_html'] += utils.add_image(img_src, link=utils.get_redirect_url(el['href']))
                        continue
            logger.warning('unhandled sqs-block-code in ' + item['url'])

        elif 'sqs-block-summary-v2' in block['class']:
            #utils.write_file(str(el), './debug/debug.html')
            el = block.find(class_='summary-heading')
            if el and re.search(r'You may also like|Featured', el.get_text(), flags=re.I):
                continue
            else:
                logger.warning('unhandled sqs-block-summary-v2 block in ' + item['url'])

        elif 'sqs-block-button' in block['class']:
            # el = block.find(class_='sqs-block-button-container')
            el = block.find('a', class_='sqs-block-button-element')
            if el:
                if re.search(r'Share on (Facebook|Twitter)', el.get_text(strip=True), flags=re.I):
                    continue
                item['content_html'] += utils.add_button(el['href'], el.get_text().strip())
            else:
                logger.warning('unhandled sqs-block-button in ' + item['url'])

        elif 'sqs-block-amazon' in block['class']:
            # https://evanmccann.net/blog/2020/11/iphone-12-mini
            if block.get('data-block-json'):
                data_json = json.loads(block['data-block-json'])
                #utils.write_file(data_json, './debug/data.json')
                item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                item['content_html'] += '<div style="flex:1; min-width:128px; max-width:160px; margin:auto;"><img src="{}" style="width:100%;" /></div>'.format(data_json['amazonProduct']['imageUrlMedium'])
                item['content_html'] += '<div style="flex:2; min-width:256px;"><div style="font-size:1.2em; font-weight:bold;">{}</div><div>By {}</div><div><a href="{}">Buy on Amazon</a></div></div>'.format(data_json['amazonProduct']['title'], data_json['amazonProduct']['manufacturer'], utils.clean_url(data_json['amazonProduct']['detailPageUrl']))
                item['content_html'] += '</div>'

        elif 'sqs-block-newsletter' in block['class'] or 'sqs-block-spacer' in block['class']:
            pass

        else:
            logger.warning('unhandled sqs-block class {} in {}'.format(block['class'], item['url']))

    # item['content_html'] = re.sub(r'</(figure|table)><(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)


def test_handler():
    feeds = ['https://www.tvrev.com/news?format=rss',
             'https://www.slacker-labs.com/blog?format=rss',
             'https://linkdhome.com/articles?format=rss']
    for url in feeds:
        get_feed({"url": url}, True)
