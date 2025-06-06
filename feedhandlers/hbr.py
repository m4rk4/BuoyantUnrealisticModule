import base64, json, re
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from datetime import datetime
from urllib.parse import urlsplit, quote_plus

import config, utils
from feedhandlers import wp_posts

import logging

logger = logging.getLogger(__name__)


def pad_string(byte_string):
    padding_char = b" "
    size = 16
    x = len(byte_string) % size
    pad_length = size - x
    return byte_string + padding_char * pad_length


def encrypt(text_string):
    key = b'303ebd5795a67119'
    iv = b'bcbd5a82e90d7cec'
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(pad_string(text_string.encode('utf-8')))
    return base64.b64encode(ciphertext).decode()


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    page_soup = BeautifulSoup(page_html, 'lxml')

    if '/podcast/' not in url:
        content = page_soup.find('content', attrs={"js-target": "article-content"})
        if not content:
            logger.warning('unable to find content in ' + url)
            return None

        key = content['data-key'] + '|' + str(int(round(datetime.now().timestamp() / 1000, 0)))
        data = {
            "contentKey": content['data-index'],
            "key": encrypt(key),
            "pageSlug": content['data-page-slug']
        }

        split_url = urlsplit(url)
        paths = list(filter(None, split_url.path[1:].split('/')))
        api_url = 'https://hbr.org/api/article/piano/content?year={}&month={}&seotitle={}'.format(paths[0], paths[1], paths[2])
        headers = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
            "content-type": "application/json",
            "priority": "u=1, i",
            "sec-ch-ua": "\"Not/A)Brand\";v=\"8\", \"Chromium\";v=\"126\", \"Microsoft Edge\";v=\"126\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "x-requested-with": "XMLHttpRequest"
        }
        content_json = utils.post_url(api_url, json_data=data, headers=headers)
        if not content_json:
            return None
        if save_debug:
            utils.write_file(content_json, './debug/content.json')
    else:
        content_json = None

    el = page_soup.find('script', string=re.compile(r'window\.digitalData'))
    if not el:
        logger.warning('unable to find window.digitalData in ' + url)
        return None

    i = el.string.find('{')
    j = el.string.find('};') + 1
    data_json = json.loads(el.string[i:j])
    if save_debug:
        utils.write_file(data_json, './debug/debug.json')

    page_attr = data_json['page']['attributes']

    item = {}
    item['id'] = page_attr['articleID']

    el = page_soup.find('meta', attrs={"property": "og:url"})
    if el:
        item['url'] = el['content']
    else:
        item['url'] = url

    item['title'] = page_attr['articleTitle']

    el = page_soup.find('meta', attrs={"property": "article:published_time"})
    if el:
        dt = datetime.fromisoformat(el['content'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    el = page_soup.find('meta', attrs={"property": "og:article:modified_time"})
    if el:
        dt = datetime.fromisoformat(el['content'])
        item['date_modified'] = dt.isoformat()

    if page_attr.get('articleAuthor'):
        authors = [it['authorName'] for it in page_attr['articleAuthor']]
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif page_attr['articleType'] == 'Audio':
        item['author'] = {"name": page_attr['podcastSeriesTitle']}
    elif page_attr['articleType'] == 'Magazine Article':
        item['author'] = {"name": "HBR Magazine"}

    item['tags'] = []
    if page_attr.get('articleSubTopics'):
        for it in page_attr['articleSubTopics']:
            item['tags'].append(it['subTopicName'])
    if page_attr.get('articleTags'):
        item['tags'] += [it.strip() for it in page_attr['articleTags'].split('|')]
    if page_attr.get('editorTags'):
        for it in page_attr['editorTags']:
            item['tags'].append(it['tagValue'])

    item['content_html'] = ''
    el = page_soup.find(class_='article-dek')
    if el and el.get_text().strip():
        item['content_html'] += '<p><em>' + el.get_text().strip() + '</em></p>'

    el = page_soup.find('meta', attrs={"property": "og:image"})
    if el:
        item['_image'] = el['content']
        if page_attr['articleType'] != 'Audio':
            captions = []
            it = page_soup.find('span', class_='caption--hero-image')
            if it and it.get_text().strip():
                captions.append(it.decode_contents().strip())
            it = page_soup.find('span', class_='credits--hero-image')
            if it and it.get_text().strip():
                captions.append(it.decode_contents().strip())
            item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    if page_attr['articleType'] == 'Audio':
        el = page_soup.find('audio', class_='podcast-post__audio-file')
        if el:
            item['_audio'] = el['src']
            attachment = {}
            attachment['url'] = item['_audio']
            attachment['mime_type'] = 'audio/mp3g'
            item['attachments'] = []
            item['attachments'].append(attachment)
            el = page_soup.find(class_='podcast-post__banner-logo')
            if el and el.img:
                poster = 'https://hbr.org' + el.img['src']
            else:
                poster = item['_image']
            el = page_soup.find(class_='podcast-post__banner-series')
            if el and el.a:
                author_url = 'https://hbr.org' + el.a['href']
            else:
                author_url = ''
            dt = datetime.fromisoformat(item['date_published'])
            item['content_html'] += utils.add_audio(item['_audio'], poster, item['title'], item['url'], item['author']['name'], author_url, utils.format_display_date(dt, date_only=True), 0)
        else:
            logger.warning('unable to find podcast audio file in ' + item['url'])

    if data_json['page']['pageInfo'].get('pageDescription'):
        item['summary'] = data_json['page']['pageInfo']['pageDescription']
        item['content_html'] += '<p><strong>Summary.</strong> ' + item['summary'] + '</p>'

    if page_attr['articleType'] == 'Audio':
        el = page_soup.find('section', id='details-section')
        if el:
            it = el.find(class_='podcast-details__date')
            if it:
                it.decompose()
            item['content_html'] += '<h2>Details</h2>' + el.decode_contents()
        el = page_soup.find('section', id='transcript-section')
        if el:
            item['content_html'] += '<h2>Transcript</h2>' + el.decode_contents()

    if content_json:
        content_soup = BeautifulSoup(content_json['content'], 'html.parser')
        el = content_soup.find(class_='translate-message')
        if el:
            el.decompose()

        for el in content_soup.find_all('hbr-component'):
            if el['type'] == 'newsletter' or el['type'] == 'podcast-promo':
                el.decompose()
            else:
                logger.warning('unhandled hbr-component type {} in {}'.format(el['type'], item['url']))

        for el in content_soup.find_all('article-ideainbrief'):
            el.attrs = {}
            el.name = 'blockquote'
            el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

        for el in content_soup.find_all('i', class_='icon'):
            if 'icon-caret-right' in el['class']:
                el.name = 'span'
                el.attrs = {}
                el.string = '❯'
            else:
                logger.warning('unhandled icon {} in {}'.format(el['class'], item['url']))

        for el in content_soup.find_all('span', class_=['qa', 'answer', 'question', 'lead-in', 'lead-in-large']):
            if 'qa' in el['class'] or 'answer' in el['class']:
                el.unwrap()
            elif 'question' in el['class'] or 'lead-in' in el['class'] or 'lead-in-large' in el['class']:
                el.attrs = {}
                el['style'] = 'font-weight:bold;'

        for el in content_soup.find_all('iframe'):
            new_html = utils.add_embed(el['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

        for el in content_soup.select('figure:has(> img[class*="wp-image"])'):
            if el.img.get('srcset'):
                img_src = utils.image_from_srcset(el.img['srcset'], 1200)
            else:
                img_src = el.img['src']
            if img_src.startswith('//'):
                img_src = 'https:' + img_src
            elif img_src.startswith('/'):
                img_src = 'https://hbr.org' + img_src
            captions = []
            it = el.find('span', class_='caption--inline-image')
            if it and it.get_text().strip():
                captions.append(it.decode_contents().strip())
            it = el.find('span', class_='credits--inline-image')
            if it and it.get_text().strip():
                captions.append(it.decode_contents().strip())
            new_html = utils.add_image(img_src, ' | '.join(captions))
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

        for el in content_soup.find_all(class_='article-callout'):
            # TODO: citation?
            it = el.find(class_='callout')
            new_html = utils.add_pullquote(it.decode_contents())
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

        item['content_html'] += str(content_soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) == 0 or paths[0] == 'the-latest':
        feed_json = utils.get_url_json('https://hbr.org/service/components/external-list/latest/0/8?format=json&id=page.external-list.the-latest&sort=publication_date')
    elif paths[0] == 'ascend':
        feed_json = utils.get_url_json('https://hbr.org/service/ascend/more-results/0/8?format=json&sort=publication_date')
    elif paths[0] == 'magazine':
        feed_json = {}
        mag_json = utils.get_url_json('https://hbr.org/service/magazine/0/8?format=json')
        if mag_json:
            mag_html = utils.get_url_html('https://hbr.org/archive-toc/' + mag_json['entry'][0]['id'])
            if mag_html:
                if save_debug:
                    utils.write_file(mag_html, './debug/debug.html')
                soup = BeautifulSoup(mag_html, 'lxml')
                el = soup.find('stream-content', attrs={"data-stream-name": "table-of-contents"})
                feed_json['entry'] = []
                for it in el.find_all('stream-item'):
                    entry = {
                        "contentType": it['data-content-type'],
                        "content": {
                            "src": it['data-url']
                        }
                    }
                    feed_json['entry'].append(entry)
    else:
        # TODO: topic feeds
        logger.warning('unhandled feed url ' + url)
        return None

    if not feed_json:
        return None
    if save_debug:
        utils.write_file(feed_json, './debug/feed.json')
    n = 0
    feed_items = []
    for entry in feed_json['entry']:
        if entry['contentType'] == 'Sponsor Content' or entry['contentType'] == 'Book' or entry['contentType'] == 'Case Study':
            continue
        entry_url = 'https://hbr.org' + entry['content']['src']
        if save_debug:
            logger.debug('getting content for ' + entry_url)
        item = get_content(entry_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
