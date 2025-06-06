import json, re
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_cffi_requests
from datetime import datetime
from urllib.parse import quote_plus

import config, utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)


def format_blocks(blocks):
    has_dropcap = False
    block_html = ''
    for block in blocks:
        start_tag = ''
        end_tag = ''
        if block['type'] == 'text':
            block_html += block['data']

        elif block['type'] == 'tag':
            if block['name'] == 'figure':
                if block['attribs'].get('itemtype'):
                    if 'ImageObject' in block['attribs']['itemtype']:
                        image = next((it for it in block['children'] if it['name'] == 'img'), None)
                        if image:
                            figcaption = next((it for it in block['children'] if it['name'] == 'figcaption'), None)
                            if figcaption:
                                caption += format_blocks(figcaption['children'])
                            elif image['attribs'].get('alt'):
                                caption = image['attribs']['alt']
                            else:
                                caption = ''
                            block_html += utils.add_image(image['attribs']['src'], caption)
                        else:
                            logger.warning('unhandled figure ImageObject')

                    elif 'MediaObject' in block['attribs']['itemtype']:
                        iframe = next((it for it in block['children'] if it['name'] == 'iframe'), None)
                        if iframe:
                            src = iframe['attribs']['src']
                            if src.startswith('/'):
                                src = 'https://www.economist.com' + src
                                block_html += '<blockquote><b>Embedded content from <a href="{0}">{0}</a></b></blockquote>'.format(src)
                            elif src.startswith('https://'):
                                block_html += utils.add_embed(src)
                            else:
                                m = re.search(r'https:[\w\./]+', src)
                                if m:
                                    block_html += utils.add_embed(m.group(0))
                                else:
                                    logger.warning('unhandled iframe src ' + src)
                        else:
                            logger.warning('unhandled figure MediaObject')

                    elif 'WPAdBlock' in block['attribs']['itemtype']:
                        continue
                else:
                    # Check if the figure wraps another figure
                    if block.get('children'):
                        figure = next((it for it in block['children'] if it['name'] == 'figure'), None)
                        if figure:
                            block_html += format_blocks([figure])
                    if not block_html:
                        logger.warning('unhandled figure')

            elif block['name'] == 'a':
                start_tag = '<a href="{}">'.format(block['attribs']['href'])
                end_tag = '</a>'

            elif block['name'] == 'span':
                if block.get('attribs') and block['attribs'].get('data-caps'):
                    start_tag = '<span style="float:left; font-size:4em; line-height:0.8em;">'
                    end_tag = '</span>'
                    has_dropcap = True
                else:
                    start_tag = '<span>'
                    end_tag = '</span>'

            elif block['name'] == 'cite':
                start_tag = utils.open_pullquote()
                end_tag = utils.close_pullquote()

            else:
                start_tag = '<{}>'.format(block['name'])
                end_tag = '</{}>'.format(block['name'])

            if start_tag:
                block_html += start_tag + format_blocks(block['children']) + end_tag
        else:
            logger.warning('unhandled block type ' + block['type'])
    if has_dropcap:
        block_html += '<span style="clear:left;">&nbsp;</span>'
    return block_html


def get_content(url, args, site_json, save_debug=False):
    if '/infographics.economist.com/' in url:
        item = {}
        item['_image'] = '{}/screenshot?url={}&locator=%23g-index-box'.format(config.server, quote_plus(url))
        item['content_html'] = utils.add_image(item['_image'], link=url)
        return item
    elif '/interactive/' in url:
        logger.warning('unhandled url ' + url)
        return None

    # page_html = utils.get_url_html(url, headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 8_3 like Mac OS X) AppleWebKit/600.1.4 (KHTML, like Gecko) Version/8.0 Mobile/12F70 Safari/600.1.4 (compatible; GrapeshotCrawler/2.0; +http://www.grapeshot.co.uk/crawler.php)"})
    page_html = utils.get_url_html(url, user_agent='grapeshot')
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')
    soup = BeautifulSoup(page_html, 'lxml')
    next_data = soup.find('script', id='__NEXT_DATA__')
    if not next_data:
        return None
    next_json = json.loads(next_data.string)
    if save_debug:
        utils.write_file(next_json, './debug/debug.json')

    item = {}
    if next_json['props']['pageProps'].get('cp2Content'):
        content_json = next_json['props']['pageProps']['cp2Content']
    elif next_json['props']['pageProps'].get('content'):
        content_json = next_json['props']['pageProps']['content']
    else:
        content_json = None

    if content_json:
        item['id'] = content_json['id']
        item['url'] = next_json['props']['pageProps']['pageUrl']

        if '/the-world-this-week/' in item['url']:
            item['title'] = 'The World this Week: {} ({})'.format(content_json['headline'], utils.format_display_date(datetime.fromisoformat(content_json['datePublished']), date_only=True))
        else:
            item['title'] = content_json['headline']

        dt = datetime.fromisoformat(content_json['datePublished'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        dt = datetime.fromisoformat(content_json['dateModified'])
        item['date_modified'] = dt.isoformat()

        if content_json.get('byline'):
            item['author'] = {
                "name": content_json['byline']
            }
        elif content_json.get('brand'):
            item['author'] = {
                "name": content_json['brand']
            }
        else:
            item['author'] = {
                "name": "The Economist"
            }
        item['authors'] = []
        item['authors'].append(item['author'])

        item['tags'] = []
        if content_json.get('section'):
            item['tags'].append(content_json['section']['name'])
        if content_json.get('tags'):
            item['tags'] += [x['name'] for x in content_json['tags']]
        if not item.get('tags'):
            del item['tags']

        if content_json['seo'].get('description'):
            item['summary'] = content_json['seo']['description']
        elif content_json.get('rubric'):
            item['summary'] = content_json['rubric']
        elif content_json.get('printRubric'):
            item['summary'] = content_json['printRubric']

        item['content_html'] = ''
        if content_json.get('rubric'):
            item['content_html'] += '<p><em>' + content_json['rubric'] + '</em></p>'
        elif content_json.get('printRubric'):
            item['content_html'] += '<p><em>' + content_json['printRubric'] + '</em></p>'

        if content_json.get('leadComponent') and content_json['leadComponent']['type'] == 'IMAGE':
            item['image'] = content_json['leadComponent']['url']
            captions = []
            if content_json['leadComponent'].get('caption') and content_json['leadComponent']['caption'].get('textHtml'):
                captions.append(content_json['leadComponent']['caption']['textHtml'])
            if content_json['leadComponent'].get('credit'):
                captions.append(content_json['leadComponent']['credit'])
            item['content_html'] += utils.add_image(item['image'], ' | '.join(captions))

        if 'embed' in args:
            item['content_html'] = utils.format_embed_preview(item)
            return item

        if content_json.get('body'):
            for block in content_json['body']:
                if block['type'] == 'PARAGRAPH':
                    if block['textHtml'].startswith('<span data-caps'):
                        item['content_html'] += '<p>' + re.sub(r'^<span[^>]+>([^<]+)</span>', r'<span style="float:left; font-size:4em; line-height:0.8em;">\1</span>', block['textHtml']) + '</p><span style="clear:left;"></span>'
                    else:
                        item['content_html'] += '<p>' + block['textHtml'] + '</p>'
                else:
                    logger.warning('unhandled body content block type {} in {}'.format(block['type'], item['url']))

    elif next_json['props']['pageProps'].get('metadata'):
        metadata = next_json['props']['pageProps']['metadata']
        item['id'] = metadata['tegID']
        item['url'] = metadata['url']
        item['title'] = metadata['headline']

        dt = datetime.fromisoformat(metadata['datePublished'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        dt = datetime.fromisoformat(metadata['dateModified'])
        item['date_modified'] = dt.isoformat()

        item['author'] = {
            "name": "The Economist"
        }
        item['authors'] = []
        item['authors'].append(item['author'])

        item['content_html'] = ''
        if metadata.get('description'):
            item['summary'] = metadata['description']
            item['content_html'] += '<p><em>' + metadata['description'] + '</em></p>'

        if metadata.get('imageUrl'):
            item['image'] = metadata['imageUrl']
            item['content_html'] += utils.add_image(metadata['imageUrl'])

        if 'embed' in args:
            item['content_html'] = utils.format_embed_preview(item)
            return item

        if next_json['props']['pageProps'].get('content') and next_json['props']['pageProps']['content'].get('gobbets'):
            for block in next_json['props']['pageProps']['content']['gobbets']:
                item['content_html'] += '<p>' + block + '</p><div>&nbsp;</div><hr/><div>&nbsp;</div>'

    if ('walled' in next_json['props']['pageProps'] and next_json['props']['pageProps']['walled'] == True) or ('isUnwalled' in next_json['props']['pageProps'] and next_json['props']['pageProps']['isUnwalled'] == False):
        item['content_html'] += '<h3 style="text-align:center;"><a href="{}">Article is paywalled</a></h3>'.format(item['url'])
        get_archive_content(item['url'], save_debug)
    return item


def get_archive_content(url, save_debug):
    # TODO: utils.get_url_html often times out
    # page_html = utils.get_url_html('https://archive.is/' + url, use_proxy=True, use_curl_cffi=True)
    # if not page_html:
    #     return None
    r = curl_cffi_requests.get('https://archive.is/' + url, impersonate=config.impersonate, proxies=config.proxies)
    if r.status_code != 200:
        return None
    page_html = r.text
    if save_debug:
        utils.write_file(page_html, './debug/archive.html')
    soup = BeautifulSoup(page_html, 'lxml')
    archive_links = []
    for el in soup.find_all('div', class_='TEXT-BLOCK'):
        if el.a['href'] not in archive_links:
            archive_links.append(el.a['href'])
    if len(archive_links) == 0:
        logger.warning(url + ' is not archived')
        return None
    archive_link = archive_links[-1]
    logger.debug('getting content from ' + archive_link)

    # TODO: utils.get_url_html often times out
    # page_html = utils.get_url_html(archive_link, use_proxy=True, use_curl_cffi=True)
    # if not page_html:
    #     return None
    r = curl_cffi_requests.get(archive_link, impersonate=config.impersonate, proxies=config.proxies)
    if r.status_code != 200:
        return None
    page_html = r.text
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')
    soup = BeautifulSoup(page_html, 'lxml')
    body = soup.select('main#content > article section')
    return None


def get_feed(url, args, site_json, save_debug=False):
    # https://www.economist.com/rss
    return rss.get_feed(url, args, site_json, save_debug, get_content)
