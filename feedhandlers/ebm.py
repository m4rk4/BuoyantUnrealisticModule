import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=960):
    if img_src.startswith('https://img.'):
        return utils.clean_url(img_src) + '?auto=format%2Ccompress&w={}'.format(width)
    elif img_src.startswith('https://cdn.'):
        return re.sub(r'\/\d+w\/', '/{}w/'.format(width), img_src)
    else:
        return img_src


def get_content(url, args, site_json, save_debug=False):
    # Content sites: https://www.endeavorbusinessmedia.com/mkts-we-serve/
    split_url = urlsplit(url)
    json_data = {
        "query": "query getWebsiteLayoutPage($alias: String!, $useCache: Boolean, $preview: Boolean, $cacheKey: String) {\n  getWebsiteLayoutPage(input: { alias: $alias, useCache: $useCache, preview: $preview, cacheKey: $cacheKey }) {\n    id\n    name\n    primaryGrid\n    secondaryGrid\n    pageData\n    cache\n    layoutType {\n      alias\n      contentType\n      type\n      propagate\n      key\n    }\n    loadMoreType {\n      type\n    }\n    created\n    usedContentIds\n    usedIssueIds\n  }\n}\n",
        "variables": {
            "alias": split_url.path,
            "useCache": True,
            "preview": False,
            "cacheKey":"v2"
        }
    }
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "authorization": "Bearer undefined",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "pragma": "no-cache",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"111\", \"Not(A:Brand\";v=\"8\", \"Chromium\";v=\"111\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "x-site-user": "Bearer undefined",
        "x-tenant-key": site_json['x-tenant-key']
    }
    post_json = utils.post_url(site_json['graphql_url'], json_data=json_data, headers=headers)
    if not post_json:
        return None
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    page_data = post_json['data']['getWebsiteLayoutPage']['pageData']

    item = {}
    item['id'] = page_data['id']
    item['url'] = page_data['siteContext']['canonicalUrl']
    item['title'] = page_data['name']

    dt = datetime.fromtimestamp(page_data['published']/1000).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromtimestamp(page_data['updated']/1000).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    authors = []
    if page_data.get('authors'):
        for it in page_data['authors']['edges']:
            authors.append(it['node']['name'])
    if authors:
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author']['name'] = split_url.netloc

    if page_data.get('taxonomy') and page_data['taxonomy'].get('edges'):
        item['tags'] = []
        for it in page_data['taxonomy']['edges']:
            item['tags'].append(it['node']['name'])

    if page_data.get('teaser'):
        item['summary'] = page_data['teaser']

    item['content_html'] = ''
    if page_data.get('deck'):
        item['content_html'] += '<p><em>{}</em></p>'.format(page_data['deck'])

    if page_data.get('primaryImage'):
        item['_image'] = page_data['primaryImage']['src']
        if page_data['__typename'] != 'ContentMediaGallery' and page_data['__typename'] != 'ContentVideo':
            captions = []
            if page_data['primaryImage'].get('caption'):
                captions.append(page_data['primaryImage']['caption'])
            if page_data['primaryImage'].get('credit'):
                captions.append(page_data['primaryImage']['credit'])
            item['content_html'] += utils.add_image(resize_image(page_data['primaryImage']['src']), ' | '.join(captions))

    if page_data['__typename'] == 'ContentVideo' and page_data.get('embedCode'):
        soup = BeautifulSoup(page_data['embedCode'], 'html.parser')
        item['content_html'] += utils.add_embed(soup.iframe['src'])

    if page_data.get('body'):
        def sub_embed_content(matchobj):
            data_json = {}
            for m in re.findall(r'([^=\s]+)="([^"]+)"', matchobj.group(1)):
                data_json[m[0]] = m[1]
            if data_json.get('data-embed-type') == 'image':
                captions = []
                if data_json.get('data-embed-caption'):
                    captions.append(data_json['data-embed-caption'])
                if data_json.get('data-embed-credit'):
                    captions.append(data_json['data-embed-credit'])
                return '</p>' + utils.add_image(resize_image(data_json['data-embed-src']), ' | '.join(captions)) + '<p>'
            elif data_json.get('data-embed-type') == 'oembed':
                return '</p>' + utils.add_embed(data_json['data-embed-id']) + '<p>'
            logger.warning('unhandled embed content')
            return matchobj.group(0)
        content = re.sub(r'%{\[\s?(.*?)\s?\]}%', sub_embed_content, page_data['body'])

        soup = BeautifulSoup(content, 'html.parser')
        for el in soup.find_all('img', attrs={"alt": True}):
            new_html = utils.add_image(resize_image(el['src']))
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            if el.parent and el.parent.name == 'p':
                el_parent = el.parent
                el.decompose()
                new_html = re.sub(r'(<figure .*?</figure>)', r'</p>\1<p>', str(el_parent))
                new_el = BeautifulSoup(new_html, 'html.parser')
                el_parent.insert_after(new_el)
                el_parent.decompose()
            else:
                el.decompose()

        for el in soup.find_all('iframe'):
            if el.get('src'):
                new_html = utils.add_embed(el['src'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                it = el.find_parent(class_='emb-video')
                if it:
                    el_parent = it
                elif el.parent and el.parent.name == 'p':
                    el_parent = el.parent
                else:
                    el_parent = el
                el_parent.insert_after(new_el)
                el_parent.decompose()
            elif el.get('name') and re.search(r'google_ads_iframe', el['name']):
                it = el.find_parent('p')
                if it:
                    it.decompose()
                else:
                    el.decompose()
            else:
                logger.warning('unhandled iframe in ' + item['url'])

        for el in soup.find_all('blockquote'):
            el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

        for el in soup.find_all('h5'):
            el.name = 'h3'

        for el in soup.find_all('aside'):
            el.decompose()

        item['content_html'] += str(soup)

    if page_data['__typename'] == 'ContentMediaGallery' and page_data.get('images'):
        for i in range(1, len(page_data['images']['edges'])):
            it = page_data['images']['edges'][i]['node']
            item['content_html'] += utils.add_image(resize_image(it['src']), it.get('credit'))
            if it.get('displayName'):
                item['content_html'] += '<h3>{}</h3>'.format(it['displayName'])
            if it.get('body'):
                item['content_html'] += '<p>{}</p>'.format(it['body'])
            elif it.get('caption'):
                item['content_html'] += '<p>{}</p>'.format(it['caption'])

    #item['content_html'] = re.sub(r'</figure>(\s*[^<])', r'</figure><div>&nbsp;</div>\1', item['content_html'])
    item['content_html'] = re.sub(r'<p>\s*(<br/>)?</p>', '', item['content_html'])
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
