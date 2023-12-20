import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    elif split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    path += '.json'

    params = []
    for i in range(len(paths)):
        if i == 0:
            params.append('section=' + paths[i])
        elif i == 1:
            params.append('category=' + paths[i])
        elif i == 3:
            params.append('detail=' + paths[i])
    if params:
        query = '?' + '&'.join(params)
    else:
        query = ''

    next_url = '{}://{}/_next/data/{}{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, query)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        if page_html:
            soup = BeautifulSoup(page_html, 'lxml')
            el = soup.find('script', id='__NEXT_DATA__')
            if el:
                next_data = json.loads(el.string)
                if next_data['buildId'] != site_json['buildId']:
                    logger.debug('updating {} buildId'.format(split_url.netloc))
                    site_json['buildId'] = next_data['buildId']
                    utils.update_sites(url, site_json)
                return next_data['props']
    return next_data


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    if 'tosshub.com' in split_url.netloc:
        if '.gif' in split_url.path:
            return img_src
        if split_url.query:
            query = parse_qs(split_url.query)
            if query.get('size'):
                del query['size']
            if query:
                return '{}://{}{}?{}&size={}:*'.format(split_url.scheme, split_url.netloc, split_url.path, urlencode(query, doseq=True), width)
            else:
                return img_src + '&size={}:*'.format(width)
        else:
            return img_src + '?size={}:*'.format(width)
    return img_src


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    page_data = next_data['pageProps']['initialState']['server']['page_data']
    item = {}
    item['id'] = page_data['id']
    item['url'] = 'https://www.indiatoday.in' + page_data['seo_detail']['canonical_url']
    item['title'] = page_data['title']

    tz_loc = pytz.timezone('Asia/Calcutta')
    dt_loc = datetime.fromisoformat(page_data['datetime_published'])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt_loc = datetime.fromisoformat(page_data['datetime_updated'])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_modified'] = dt.isoformat()

    if page_data.get('author'):
        authors = []
        for it in page_data['author']:
            authors.append(it['title'])
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if page_data['seo_detail'].get('meta_keyword'):
        item['tags'] = [it.strip() for it in page_data['seo_detail']['meta_keyword'].split(',')]

    # TODO: tag, topic

    item['content_html'] = ''

    if page_data['type'] == 'video embed':
        if page_data.get('mp4_url'):
            item['content_html'] += utils.add_video(page_data['mp4_url'][0]['video_url'], 'video/mp4', resize_image(page_data['image_main']), item['title'])
        elif page_data.get('hls_url'):
            item['content_html'] += utils.add_video(page_data['hls_url'][0]['video_url'], 'application/x-mpegURL', resize_image(page_data['image_main']), item['title'])
        return item

    if page_data.get('description_short'):
        item['summary'] = page_data['description_short']
        item['content_html'] += '<p><em>{}</em></p>'.format(page_data['description_short'])

    if page_data['content_type'] == 'video':
        if page_data.get('mp4_url'):
            item['content_html'] += utils.add_video(page_data['mp4_url'][0]['video_url'], 'video/mp4', resize_image(page_data['image_main']))
        elif page_data.get('hls_url'):
            item['content_html'] += utils.add_video(page_data['hls_url'][0]['video_url'], 'application/x-mpegURL', resize_image(page_data['image_main']))
    elif page_data.get('image_sixteen_nine_gif'):
        item['_image'] = page_data['image_sixteen_nine_gif']
    elif page_data.get('image_main'):
        item['_image'] = page_data['image_main']
    if item.get('_image'):
        captions = []
        if page_data.get('image_caption'):
            captions.append(page_data['image_caption'])
        if page_data.get('image_credit'):
            captions.append(page_data['image_credit'])
        item['content_html'] += utils.add_image(resize_image(item['_image']), ' | '.join(captions))

    if page_data.get('tech_pros_cons') and page_data['tech_pros_cons'].get('tech_review_desc'):
        soup = BeautifulSoup(page_data['tech_pros_cons']['tech_review_desc'], 'html.parser')
        el = soup.find(id='reviewcontainer')
        if el:
            el.unwrap()
        el = soup.find(class_='techreview')
        if el:
            el.unwrap()
        el = soup.find('span', class_='rating')
        if el:
            # el['style'] = 'float:right; font-size:2em;'
            el.name = 'div'
            el['style'] = 'text-align:center; font-size:2em; font-weight:bold;'
            el.parent.insert_after(el)
        new_el = soup.new_tag('div')
        new_el['style'] = 'display:flex; flex-wrap:wrap; gap:1em;'
        el = soup.find(class_='reviewPro')
        if el:
            el['style'] = 'flex:1; min-width:256px;'
            new_el.append(el)
        el = soup.find(class_='reviewCons')
        if el:
            el['style'] = 'flex:1; min-width:256px;'
            new_el.append(el)
        soup.append(new_el)
        item['content_html'] += str(soup)

    if page_data.get('factcheck') and page_data['factcheck'].get('claim_text'):
        item['content_html'] += '<h2>India Today Fact Check</h2>'
        item['content_html'] += '<div style="margin:0 8px 0 8px; padding:0 1em; 0 1em; border:1px solid black;"><p><span style="font-size:1.2em; font-weight:bold;">Claim:</span><br/>{}</span></p>'.format(page_data['factcheck']['claim_text'])
        colors = ['Red', 'Orange', 'GreenYellow', 'LimeGreen']
        item['content_html'] += '<p style="font-size:1.2em; font-weight:bold; color:{}">{}</p>'.format(colors[int(page_data['factcheck']['review_rating']) - 1], page_data['factcheck']['alternate_name'])
        item['content_html'] += '<p><span style="font-size:1.2em; font-weight:bold;">Fact:</span><br/>{}</span></p></div>'.format(page_data['factcheck']['conclusion_text'])

    if page_data.get('highlight'):
        item['content_html'] += '<h3>In Short</h3><ul>'
        for it in page_data['highlight']:
            item['content_html'] += '<li>{}</li>'.format(it['title'])
        item['content_html'] += '</ul><hr style="width:50%; margin:auto;"/>'

    soup = BeautifulSoup(page_data['description'], 'html.parser')
    for el in soup.find_all(class_=['authors__container', 'dottedimg']):
        el.decompose()

    for el in soup.find_all(id=['tab-link-wrapper-plugin', 'tab-video-wrapper-plugin']):
        el.decompose()

    for el in soup.find_all(class_='field--type-text-with-summary'):
        el.unwrap()

    for el in soup.find_all(class_='pointer-section'):
        for i, para in enumerate(el.find_all(class_='pointer-para')):
            num = soup.new_tag('span')
            num['style'] = 'float:left; font-size:3em; line-height:0.8em; color:red; padding-right:12px;'
            num.string = str(i + 1).zfill(2)
            para.p.insert(0, num)
            para.unwrap()
        for it in el.find_all(['ul', 'li']):
            it.unwrap()
        for it in el.find_all(class_=['field--name-field-listicle-description', 'field__item']):
            it.unwrap()
        el.unwrap()

    for el in soup.find_all('figure', class_='caption-drupal-entity'):
        it = el.find('figcaption')
        if it:
            caption = it.decode_contents()
        else:
            caption = ''
        it = el.find(class_='itgimage')
        new_html = utils.add_image(resize_image(it.img['src']), caption)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='embedded-entity'):
        new_html = ''
        if el.get('data-embed-button') and el['data-embed-button'] == 'ckeditor_image':
            it = el.find('img')
            if it:
                # TODO: caption
                new_html = utils.add_image(resize_image(it['src']))
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled embedded-entity in ' + item['url'])

    for el in soup.find_all(class_='poductphotoby__widget'):
        new_html = ''
        it = el.find(class_='photoby__title')
        if it:
            new_html += '<h2>{}</h2>'.format(it.get_text())
        for it in el.find_all(class_='itgimage'):
            new_html += utils.add_image(resize_image(it.img['src']))
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='itgimage'):
        if el.img['src'].startswith('data:image/png;base64,'):
            el.decompose()
            continue
        new_html = utils.add_image(resize_image(el.img['src']))
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='embedcode'):
        new_html = ''
        if el.find(class_='twitter-tweet'):
            links = el.find_all('a')
            new_html = utils.add_embed(links[-1]['href'])
        elif el.find(class_='instagram-media'):
            it = el.find('blockquote')
            new_html = utils.add_embed(it['data-instgrm-permalink'])
        elif el.find('iframe'):
            new_html = utils.add_embed(el.iframe['src'])
        else:
            for it in el.find_all('script'):
                it.decompose()
            if len(el.contents) == 0:
                el.decompose()
                continue
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled embedcode in ' + item['url'])

    for el in soup.find_all(class_='youtube-embed-wrapper'):
        it = el.find('iframe')
        new_html = utils.add_embed(it['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.select('p > iframe'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        it = el.find_parent('p')
        it.insert_after(new_el)
        it.decompose()

    for el in soup.select('article > div.custom-media-docs > iframe.custom-video-iframe-cls'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        it = el.find_parent('article')
        it.insert_after(new_el)
        it.decompose()

    item['content_html'] += re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', str(soup))
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    page_data = next_data['pageProps']['initialState']['server']['page_data']
    urls = []
    for content in page_data['content']:
        content_url = 'https://www.indiatoday.in' + content['canonical_url']
        urls.append(content_url)
    for it in page_data['left']+ page_data['right']:
        for widget in it:
            for content in widget['content']:
                if isinstance(content, dict):
                    if content['content_type'] == 'story' or content['content_type'] == 'video' or content['content_type'] == 'photo_gallery':
                        content_url = 'https://www.indiatoday.in' + content['canonical_url']
                        urls.append(content_url)
                    elif content['content_type'] == 'html_widgets' or content['content_type'] == 'breaking_news':
                        continue
                    else:
                        logger.warning('unhandled page content {} in {}'.format(content['content_type'], url))

    n = 0
    feed_items = []
    for content_url in urls:
        if save_debug:
            logger.debug('getting content for ' + content_url)
        item = get_content(content_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    if page_data.get('title'):
        feed['title'] = page_data['title'] + ' | indiatoday.in'
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed