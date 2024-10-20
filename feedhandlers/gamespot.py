import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import unquote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')

    ld_json = None
    for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
        ld_json = json.loads(el.string)
        if ld_json.get('@type') and ld_json['@type'] == 'NewsArticle':
            break
        else:
            ld_json = None

    page_data = None
    if '/articles/' in url:
        headers = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "en-US,en;q=0.9",
            "cache-control": "no-cache",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "pragma": "no-cache",
            "sec-ch-ua": "\"Microsoft Edge\";v=\"119\", \"Chromium\";v=\"119\", \"Not?A_Brand\";v=\"24\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
            "x-requested-with": "XMLHttpRequest"
        }
        page_data = utils.post_url(url, data={'ajax': 1}, headers=headers)
        if not page_data:
            return None
        soup = BeautifulSoup(page_data['content'], 'html.parser')

    if not page_data and not ld_json:
        return None

    if save_debug:
        if page_data:
            utils.write_file(page_data, './debug/debug.json')
        if ld_json:
            utils.write_file(ld_json, './debug/ld_json.json')
        utils.write_file(str(soup), './debug/debug.html')

    item = {}
    if page_data:
        item['id'] = page_data['guid']
        item['url'] = 'https://www.gamespot.com' + page_data['url']
        item['title'] = page_data['title']
    elif ld_json:
        item['id'] = paths[-1]
        item['url'] = ld_json['url']
        item['title'] = ld_json['headline']

    if ld_json and ld_json.get('datePublished'):
        dt = datetime.fromisoformat(ld_json['datePublished'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        if ld_json.get('dateModified'):
            dt = datetime.fromisoformat(ld_json['dateModified'])
            item['date_modified'] = dt.isoformat()
    else:
        el = soup.find('time', attrs={"datetime": True})
        if el:
            dt = datetime.fromisoformat(el['datetime']).astimezone(timezone.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)

    if ld_json and ld_json.get('author'):
        item['author'] = {
            "name": ld_json['author']['name']
        }
        item['authors'] = []
        item['authors'].append(item['author'])
    else:
        item['authors'] = []
        for el in soup.find_all(class_='byline-author__name'):
            item['authors'].append({"name": el.get_text().strip()})
        if len(item['authors']) > 0:
            item['author'] = {
                "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
            }

    if page_data:
        item['tags'] = []
        if page_data['tracking']['google_tag_manager']['data'].get('topicName'):
            item['tags'] += page_data['tracking']['google_tag_manager']['data']['topicName']
        if page_data['tracking']['google_tag_manager']['data'].get('productName'):
            item['tags'].append(page_data['tracking']['google_tag_manager']['data']['productName'])
        if page_data['tracking']['google_tag_manager']['data'].get('productGenre'):
            item['tags'] += page_data['tracking']['google_tag_manager']['data']['productGenre']
        if page_data['tracking']['google_tag_manager']['data'].get('productPlatform'):
            item['tags'] += page_data['tracking']['google_tag_manager']['data']['productPlatform']
    # TODO: ld_json['keywords']

    if ld_json and ld_json.get('image'):
        item['image'] = ld_json['image']['url']

    if ld_json and ld_json.get('description'):
        item['summary'] = ld_json['description']

    item['content_html'] = ''
    el = soup.find(class_='news-deck')
    if el:
        if 'summary' not in item:
            item['summary'] = el.get_text()
        item['content_html'] += '<p><em>' + el.get_text() + '</em></p>'

    el = soup.find(id='kubrick-lead')
    if el and el.get('style'):
        m = re.search(r'background-image:\s?url\(([^\)]+)\)', el['style'])
        if m:
            item['image'] = m.group(1)
            item['content_html'] += utils.add_image(item['image'])
    elif 'image' in item:
        item['content_html'] += utils.add_image(item['image'])

    if '/articles/' in item['url']:
        body = soup.find(class_='content-entity-body')
    elif '/gallery/' in item['url']:
        body = soup.find('section', class_='image-gallery')
    elif '/reviews/' in item['url']:
        body = soup.find(class_='js-content-entity-body')

    if body:
        for el in body.find_all(class_=['mapped-ad', 'article-related-video', 'image-gallery__list-item-aside']):
            el.decompose()

        for el in body.find_all(attrs={"data-embed-type": True}):
            new_html = ''
            if el['data-embed-type'] == 'image':
                if el.get('data-img-src'):
                    it = el.find('figcaption')
                    if it:
                        caption = it.decode_contents()
                    else:
                        caption = ''
                    new_html = utils.add_image(el['data-img-src'], caption)
            elif el['data-embed-type'] == 'gallery':
                if el.get('data-img-src'):
                    it = el.find(class_='image-gallery__label')
                    if it:
                        new_html += '<h2>' + it.decode_contents() + '</h2>'
                    for it in  el['data-img-src'].split(','):
                        new_html += utils.add_image(it)
            elif el['data-embed-type'] == 'imageGallery':
                # Seems to be related gallery
                el.decompose()
                continue
            elif el['data-embed-type'] == 'video':
                if el.get('data-src') and 'youtube' in el['data-src']:
                    new_html = utils.add_embed(el['data-src'])
                else:
                    it = el.find(class_='js-video-player-new')
                    if it and it.get('data-jw-media-id'):
                        new_html = utils.add_embed('https://content.jwplatform.com/players/{}.html'.format(it['data-jw-media-id']))
            elif el['data-embed-type'] == 'tweet':
                new_html = utils.add_embed(el['data-src'])
            elif el['data-embed-type'] == 'buylink':
                if el['data-size'] == 'buylink__large':
                    for it in el.find_all('input', class_='buylink__extra'):
                        it.decompose()
                    for it in el.find_all('a'):
                        if it.get('data-vars-buy-link'):
                            link = it['data-vars-buy-link']
                        else:
                            link = it['href']
                        if it.get('class') and 'buylink__link--not-button' not in it['class']:
                            it.attrs = {}
                            it['style'] = 'display:inline-block; padding:0 8px 0 8px; background-color:red; color:white; text-decoration:none;'
                        else:
                            it.attrs = {}
                        it['href'] = link
                    for i, it in enumerate(el.find_all(class_='buylink__item')):
                        if i > 0:
                            new_html += '<hr style="width:80%;" />'
                        new_html += '<table><tr>'
                        elm = it.find('img', class_='buylink__image')
                        if elm:
                            new_html += '<td style="width:128px;"><img src="{}" style="width:100%;" /></td>'.format(elm['src'])
                        new_html += '<td style="vertical-align:top;">'
                        elm = it.find(class_='buylink__title')
                        if elm:
                            new_html += '<div style="font-size:1.1em; font-weight:bold;">' + elm.decode_contents() + '</div>'
                        elm = it.find(class_='buylink__deck')
                        if elm:
                            elm.attrs = {}
                            new_html += str(elm)
                        elm = el.find(class_='buylink__links')
                        if elm:
                            for link in it.find_all('a'):
                                new_el = soup.new_tag('div')
                                new_el['style'] = 'line-height:2em; margin:8px 0 8px 0;'
                                link.wrap(new_el)
                            # it.attrs = {}
                            # it['style'] = 'line-height:2em;'
                            # new_html += str(it)
                            new_html += elm.decode_contents()
                        new_html += '</td></tr></table>'
                    new_html += '<hr/>'
                elif el['data-size'] == 'buylink__listicle':
                    for it in el.find_all('a'):
                        if it.get('data-vars-buy-link'):
                            link = it['data-vars-buy-link']
                        else:
                            link = it['href']
                        if it.get('class') and 'buylink__link--not-button' not in it['class']:
                            it.attrs = {}
                            it['style'] = 'display:inline-block; padding:0 8px 0 8px; background-color:red; color:white; text-decoration:none;'
                        else:
                            it.attrs = {}
                        it['href'] = link
                    for it in el.find_all(class_='buylink-item-container'):
                        elm = it.find(class_='image-container')
                        if elm and elm.img:
                            new_el = BeautifulSoup(utils.add_image(elm.img['src'], link=it.a['href']), 'html.parser')
                            elm.replace_with(new_el)
                        elm = it.find(class_='item-description')
                        if elm:
                            elm.unwrap()
                        elm = it.find(class_='item-buttons')
                        if elm:
                            for link in elm.find_all('div', recursive=False):
                                link['style'] = 'line-height:2em; margin:8px 0 8px 0; text-align:center;'
                            elm.unwrap()
                        it.attrs = {}
                        it['style'] = 'width:90%; margin:auto;'
                        new_html += '<hr style="width:80%; margin:auto;"/>' + str(it)
                    new_html += '<hr style="width:80%; margin:auto;"/>'
                elif el['data-size'] == 'buylink__small':
                    if el.get('data-collection'):
                        data_json = json.loads(unquote_plus(el['data-collection']))
                        new_html = '<div style="line-height:2em;"><span style="display:inline-block; padding:0 8px 0 8px; background-color:red;"><a href="{}" style="text-decoration:none; color:white;">{}</a></span></div>'.format(data_json['rawUrl'], data_json['text'])
                elif el['data-size'] == 'buylink__embed':
                    if el.get('data-collection'):
                        data_json = json.loads(unquote_plus(el['data-collection']))
                        new_html = '<a href="{}">{}</a>'.format(data_json['rawUrl'], data_json['text'])
            elif el['data-embed-type'] == 'pinbox':
                el.decompose()
                continue
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled data-embed-type {} in {}'.format(el['data-embed-type'], item['url']))

        for el in body.select('div.js-image-gallery__list-wrapper > div[data-item-position-url]'):
            new_html = ''
            it = el.find(class_='image-gallery__list-item-content')
            if it:
                for elm in it.find_all('figure'):
                    new_el = BeautifulSoup(utils.add_image(elm.img['src']), 'html.parser')
                    elm.replace_with(new_el)
                elm = it.find(class_='image-gallery__list-deck')
                if elm:
                    elm.unwrap()
                new_html = it.decode_contents()
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled js-image-gallery__list-wrapper in {}'.format(item['url']))

        for el in body.find_all(class_='js-image-gallery__list-wrapper'):
            el.unwrap()

        for el in body.find_all('a', href=re.compile(r'go\.skimresources\.com|howl\.me')):
            link = utils.get_redirect_url(el['href'])
            style = el.get('style')
            el.attrs = {}
            el['href'] = link
            el['style'] = style

        item['content_html'] += body.decode_contents()

    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://www.gamespot.com/feeds/
    return rss.get_feed(url, args, site_json, save_debug, get_content)
