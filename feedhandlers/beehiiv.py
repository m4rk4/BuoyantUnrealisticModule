import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://fossweekly.beehiiv.com/p/foss-weekly-34-another-risc-v-laptop-android-14-updates-from-peertube-and-thunderbird?_data=routes%2Fp%2F%24slug
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if split_url.netloc == 'embeds.beehiiv.com':
        # https://embeds.beehiiv.com/cab8e4a5-a66e-4cb2-b422-2e720e99d4fc
        api_url = 'https://embeds.beehiiv.com/api/embeds' + split_url.path
        api_json = utils.get_url_json(api_url)
        if api_json:
            item = {}
            item['id'] = api_json['id']
            item['url'] = url
            item['title'] = api_json['name']
            dt = datetime.fromisoformat(api_json['created_at'])
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)
            if api_json.get('updated_at'):
                dt = datetime.fromisoformat(api_json['updated_at'])
                item['date_modified'] = dt.isoformat()
            item['author'] = {
                "name": api_json['publication_id']
            }
            item['authors'] = []
            item['authors'].append(item['author'])
            item['content_html'] = '<div style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding-bottom:8px; border:1px solid {0}; border-radius:10px; background-color:{0};">'.format(api_json['config']['background_color'])
            item['content_html'] += '<h3 style="text-align:center; color:{}">{}</h3>'.format(api_json['config']['text_color'], item['title'])
            if api_json.get('description'):
                item['summary'] = api_json['description']
                item['content_html'] += '<p style="text-align:center; color:{}">{}</p>'.format(api_json['config']['text_color'], item['summary'])
            item['content_html'] += utils.add_button(item['url'], api_json['button_text'], button_color=api_json['config']['button_color'], text_color=api_json['config']['button_text_color'])
            item['content_html'] += '</div>'
            return item

    api_url = url + '?_data=routes%2F{}%2F%24slug'.format(paths[0])
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')
    post_json = api_json['post']

    item = {}
    item['id'] = post_json['id']
    item['url'] = api_json['requestUrl']
    item['title'] = post_json['meta_default_title']

    dt = datetime.fromisoformat(post_json['created_at'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post_json['updated_at'])
    item['date_modified'] = dt.isoformat()

    authors = []
    for it in post_json['authors']:
        authors.append(it['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if post_json.get('image_url'):
        item['_image'] = post_json['image_url']

    if post_json.get('meta_default_description'):
        item['summary'] = post_json['meta_default_description']

    item['content_html'] = ''
    if post_json.get('web_subtitle'):
        item['content_html'] += '<p><em>{}</em></p>'.format(post_json['web_subtitle'])

    soup = BeautifulSoup(post_json['html'], 'lxml')
    content = soup.find(id='content-blocks')
    if content:
        if save_debug:
            utils.write_file(content.decode_contents(), './debug/debug.html')

        if site_json:
            if site_json.get('rename'):
                for it in site_json['rename']:
                    for el in utils.get_soup_elements(it, content):
                        el.name = it['name']

            if site_json.get('replace'):
                for it in site_json['replace']:
                    for el in utils.get_soup_elements(it, content):
                        el.replace_with(BeautifulSoup(it['new_html'], 'html.parser'))

            if site_json.get('decompose'):
                for it in site_json['decompose']:
                    for el in utils.get_soup_elements(it, content):
                        el.decompose()

            if site_json.get('unwrap'):
                for it in site_json['unwrap']:
                    for el in utils.get_soup_elements(it, content):
                        el.unwrap()

        for el in content.find_all(['script', 'style']):
            el.decompose()

        for el in content.select('div:has( a[href*="/subscribe"]:has(> button))', recursive=False):
            el.decompose()

        # Remove different fonts and colors
        for el in content.find_all('span', attrs={"style": re.compile(r'(color|font-family):')}):
            el['style'] = re.sub(r'(color|font-family):[^;]+(;|$)', '', el['style'])

        for el in content.find_all(recursive=False):
            it = el.find(class_='button')
            if not it:
                it = el.find('button')
            if it:
                if re.search(r'Subscribe', it.get_text().strip(), flags=re.I):
                    el.decompose()
                    continue

            it = el.find(class_='twitter-wrapper')
            if it:
                links = it.find_all('a')
                new_html = utils.add_embed(links[-1]['href'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
                continue

            it = el.find('iframe')
            if it:
                new_html = utils.add_embed(it['src'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
                continue

            it = el.find('img')
            if it and it.get('style'):
                m = re.search(r'width:\s?(\d+)%', it['style'])
                if m and int(m.group(1)) >= 50:
                    img_src = it['src']
                    if it.find('small'):
                        caption = it.get_text().strip()
                    else:
                        caption = ''
                    if it.parent and it.parent.name == 'a':
                        link = it.parent['href']
                    else:
                        link = ''
                    new_html = utils.add_image(img_src, caption, link=link)
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.insert_after(new_el)
                    el.decompose()
                    continue

            it = el.select('a:has(> button)')
            if it:
                m = re.search(r'background-color:([^;]+)', it[0].button['style'])
                if m:
                    btn_color = m.group(1)
                else:
                    btn_color = 'light-dark(#ccc, #333)'
                m = re.search(r';color:([^;]+)', it[0].button['style'])
                if m:
                    color = m.group(1)
                else:
                    color = 'white'
                new_html = utils.add_button(it[0]['href'], it[0].button.decode_contents(), btn_color, color)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
                continue

            if el.name == 'div' and el.get('style'):
                it = el.find('div', attrs={"style": re.compile(r'-user-select:')})
                if it and it.get_text().strip() == '❝':
                    it = el.find('small')
                    if it:
                        author = it.decode_contents()
                    else:
                        author = ''
                    quote = ''
                    for it in el.find_all('p'):
                        it.attrs = {}
                        quote += str(it)
                    new_html = utils.add_pullquote(quote, author)
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.replace_with(new_el)
                elif 'background-color:#' in el['style']:
                    el['style'] = re.sub(r'background-color:[^;]+;', '', el['style'])
                    el['style'] += 'border:1px solid light-dark(#ccc, #333);border-radius:10px;'
                else:
                    el.unwrap()
                continue

        for el in content.find_all(['p', 'h1', 'h2', 'h3', 'ol', 'ul', 'li']):
            el.attrs = {}

        for el in content.find_all('div', attrs={"style": re.compile(r'border-top:\s?[^;]+dashed')}):
            el.insert_after(soup.new_tag('hr'))
            el.decompose()

        for el in content.find_all('a', href=re.compile(r'flight\.beehiiv\.net/v2/clicks')):
            link = utils.get_redirect_url(el['href'])
            el.attrs = {}
            el['href'] = link

        item['content_html'] += content.decode_contents()
    return item


def get_feed(url, args, site_json, save_debug=False):
    #
    if url.startswith('https://rss.beehiiv.com'):
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    split_url = urlsplit(url)
    api_url = '{}://{}?_data=routes%2Findex'.format(split_url.scheme, split_url.netloc)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    n = 0
    feed_items = []
    feed = utils.init_jsonfeed(args)
    for post in api_json['paginatedPosts']['posts']:
        url = '{}://{}/p/{}'.format(split_url.scheme, split_url.netloc, post['slug'])
        if save_debug:
            logger.debug('getting content from ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed['items'] = feed_items.copy()
    return feed
