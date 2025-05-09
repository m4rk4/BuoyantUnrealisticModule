import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1080):
    return utils.clean_url(img_src) + '?format={}w'.format(width)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    page_json = utils.get_url_json('{}://{}{}?format=json-pretty'.format(split_url.scheme, split_url.netloc, split_url.path))
    if not page_json:
        return None
    if save_debug:
        utils.write_file(page_json, './debug/debug.json')

    post_json = page_json['item']

    item = {}
    item['id'] = post_json['id']
    item['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, post_json['fullUrl'])
    item['title'] = post_json['title']

    # TODO: check timezone
    tz_loc = pytz.timezone('US/Eastern')
    dt_loc = datetime.fromtimestamp(post_json['publishOn']/1000)
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if post_json.get('updatedOn'):
        dt_loc = datetime.fromtimestamp(post_json['updatedOn']/1000)
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_modified'] = dt.isoformat()

    item['author'] = {
        "name": post_json['author']['displayName']
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

    if post_json.get('excerpt'):
        soup = BeautifulSoup(post_json['excerpt'], 'html.parser')
        item['summary'] = soup.get_text()

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    item['content_html'] = ''

    if post_json.get('promotedBlock'):
        soup = BeautifulSoup(post_json['promotedBlock'] + post_json['body'], 'html.parser')
    else:
        soup = BeautifulSoup(post_json['body'], 'html.parser')

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
    if 'image' in item and 'sqs-block-image' not in blocks[0]['class'] and 'sqs-block-video' not in blocks[0]['class'] and 'skip_lede_img' not in args:
        item['content_html'] += utils.add_image(item['image'])

    for block in blocks:
        if 'sqs-block-html' in block['class'] or 'sqs-block-markdown' in block['class']:
            for el in block.find_all('p'):
                if re.search(r'^By {}'.format(item['author']['name']), el.get_text().strip(), flags=re.I):
                    el.decompose()
                    break
            el = block.find('div', class_='sqs-block-content')
            item['content_html'] += el.decode_contents()

        elif 'sqs-block-image' in block['class']:
            if block.find(class_='sqs-empty'):
                continue
            el = block.find(class_='image-caption')
            if el:
                caption = el.get_text().strip()
            else:
                caption = ''
            el = block.find('a', class_='sqs-block-image-link')
            if el:
                link = el['href']
            else:
                link = ''
            img_src = ''
            el = block.find('img', attrs={"data-src": True})
            if el:
                img_src = el['data-src']
            else:
                el = block.find('img', attrs={"src": True})
                if el:
                    img_src = el['src']
            if img_src:
                item['content_html'] += utils.add_image(el['data-src'], caption, link=link)
                el = block.find(class_='image-card')
                if el:
                    card_html = ''
                    it = el.find(class_='image-title')
                    if it:
                        card_html += '<h4>{}</h4>'.format(it.get_text().strip())
                    it = el.find(class_='image-subtitle')
                    if it:
                        card_html += it.decode_contents()
                    it = el.find(class_='image-button')
                    if it:
                        if it.a:
                            card_html += '<a href="{}">{}</a>'.format(utils.get_redirect_url(it.a['href']), it.get_text().strip())
                    item['content_html'] += utils.add_blockquote(card_html)
            else:
                #print(block)
                logger.warning('unhandled sqs-block-image in ' + item['url'])

        elif 'sqs-block-gallery' in block['class']:
            # https://www.tokyocowboy.co/articles/uy1r8j003qdvb4ozr4qgplhd3yujyn
            # TODO: captions. Need and example.
            gallery_images = []
            gallery_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
            el = block.find(class_='sqs-gallery')
            for it in el.find_all('noscript'):
                img_src = resize_image(it.img['src'], 1200)
                thumb = resize_image(it.img['src'], 640)
                gallery_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, link=img_src) + '</div>'
                gallery_images.append({"src": img_src, "caption": '', "thumb": thumb})
            gallery_html += '</div>'
            gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
            item['content_html'] += '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + gallery_html

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
            if block.find(class_='adsbygoogle'):
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
            el = block.find(class_='sqs-block-button-container')
            if el:
                if re.search(r'Share on (Facebook|Twitter)', el.get_text(), flags=re.I):
                    continue
                style = 'width:80%; margin-right:auto; margin-left:auto; padding:8px; border-style:solid; background-color:grey; font-size:1.2em; weight:bold;'
                if el['data-alignment'] == 'center':
                    style += ' text-align:center;'
                el.attrs = {}
                el['style'] = style
                if el.a:
                    href = el.a['href']
                    # https://www.aboveavalon.com/notes/2023/5/19/youtube-gaining-tv-momentum-value-of-ad-supported-tiers-in-paid-video-streaming-apple-tv-and-ads
                    if not re.search(r'https://app\.moonclerk\.com/pay/', href):
                        el.a.attrs = {}
                        el.a['href'] = href
                        el.a['style'] = 'text-decoration:none; color:white;'
                        el['onclick'] = "location.href='{}'".format(href)
                        item['content_html'] += str(el)
                else:
                    item['content_html'] += str(el)
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

    item['content_html'] = re.sub(r'</(figure|table)><(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)


def test_handler():
    feeds = ['https://www.tvrev.com/news?format=rss',
             'https://www.slacker-labs.com/blog?format=rss',
             'https://linkdhome.com/articles?format=rss']
    for url in feeds:
        get_feed({"url": url}, True)
