import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit, quote_plus

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1024):
    split_url = urlsplit(img_src)
    m = re.search(r'(v=\d+)', split_url.query)
    if not m:
        logger.warning('unhandled image src ' + img_src)
        return img_src
    return '{}://{}{}?{}&w={}'.format(split_url.scheme, split_url.netloc, split_url.path, m.group(1), width)


def render_content(content):
    if isinstance(content, str):
        return content

    content_html = ''
    if re.search(r'^(div|em|h\d|li|ol|p|sub|sup|strong|ul)$', content['tagName']):
        content_html += '<{}>'.format(content['tagName'])
        for child in content['children']:
            content_html += render_content(child)
        content_html += '</{}>'.format(content['tagName'])

    elif re.search(r'^(br|hr)$', content['tagName']):
        content_html += '<{}/>'.format(content['tagName'])

    elif content['tagName'] == 'a':
        if content['attributes']['href'].startswith('/'):
            href = 'https://www.cnbc.com' + content['attributes']['href']
        else:
            href = content['attributes']['href']
        content_html += '<a href="{}">'.format(href)
        for child in content['children']:
            content_html += render_content(child)
        content_html += '</a>'

    elif content['tagName'] == 'subtitle':
        content_html += '<h2>'
        for child in content['children']:
            content_html += render_content(child)
        content_html += '</h2>'

    elif content['tagName'] == 'blockquote':
        quote = ''
        for child in content['children']:
            quote += render_content(child)
        content_html += utils.add_blockquote(quote)

    elif content['tagName'] == 'pullquote':
        quote = ''
        title = ''
        author = ''
        for child in content['children']:
            if child['tagName'] == 'pullquote_quote':
                for it in child['children']:
                    quote += render_content(it)
            elif child['tagName'] == 'pullquote_title':
                for it in child['children']:
                    title += render_content(it)
            elif child['tagName'] == 'pullquote_attribution':
                for it in child['children']:
                    author += render_content(it)
            else:
                logger.warning('unhandled ' + child['tagName'])
        if title:
            author += ', ' + title
        content_html += utils.add_pullquote(quote, author)

    elif content['tagName'] == 'image' or content['tagName'] == 'infographic':
        captions = []
        if content['attributes'].get('caption'):
            captions.append(content['attributes']['caption'])
        if content['attributes'].get('copyrightHolder'):
            captions.append(content['attributes']['copyrightHolder'])
        img_src = resize_image(content['attributes']['url'])
        content_html += utils.add_image(img_src, ' | '.join(captions))

    elif content['tagName'] == 'cnbcvideo':
        if content['data'].get('image'):
            poster = content['data']['image']['url']
        elif content['data'].get('promoImage'):
            poster = content['data']['promoImage']['url']
        elif content['data'].get('thumbnail'):
            poster = content['data']['thumbnail']
        else:
            poster = ''
        caption = 'Watch: <a href="{}">{}</a>'.format(content['data']['url'], content['data']['headline'])
        content_html += utils.add_video(content['data']['playbackURL'], 'application/x-mpegURL', poster, caption)

    elif content['tagName'] == 'service-embed':
        if content['attributes']['type'] == 'twitter' or content['attributes']['type'] == 'youtube':
            content_html += utils.add_embed(content['attributes']['src'])
        else:
            logger.warning('unhandled service-embed type ' + content['attributes']['type'])

    elif content['tagName'] == 'dataviz':
        if content['attributes']['library'] == 'datawrapper':
            if content['attributes'].get('altImage'):
                img_src = resize_image(content['attributes']['altImage']['url'])
                content_html += utils.add_image(img_src)
            else:
                m = re.search(r'src="([^"]+)"', content['attributes']['wildcard']['wildcardPromo']['cdata'])
                content_html += utils.add_embed(m.group(1))
        else:
            logger.warning('unhandled dataviz library ' + content['attributes']['library'])

    elif content['tagName'] == 'chart':
        if content['attributes']['chartType'] == 'stock':
            symbols = []
            for it in content['attributes']['tickerIssueDetails']:
                symbols.append(it['symbol'])
            quote_url = 'https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols={}&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json&events=1'.format(quote_plus('|'.join(symbols)))
            quote_json = utils.get_url_json(quote_url)
            if quote_json:
                content_html += '<h3>{}</h3><table style="width:100%; border:1px solid black; border-collapse:collapse;"><tr><th style="text-align:left;">Ticker</th><th style="text-align:left;">Company</th>'.format(content['attributes']['title'])
                for it in content['attributes']['headers']:
                    content_html += '<th>{}</th>'.format(it)
                content_html += '</tr>'
                for i, it in enumerate(quote_json['FormattedQuoteResult']['FormattedQuote']):
                    if i%2 == 0:
                        color = 'lightgray'
                    else:
                        color = 'none'
                    content_html += '<tr style="background-color:{};"><td>{}</td>'.format(color, it['symbol'])
                    content_html += '<td>{}</td>'.format(it['name'])
                    content_html += '<td style="text-align:center;">{}</td>'.format(it['last'])
                    content_html += '<td style="text-align:center;">{}</td>'.format(it['change'])
                    content_html += '<td style="text-align:center;">{}</td></tr>'.format(it['change_pct'])
                content_html += '</table>'
        else:
            logger.warning('unhandled chart type ' + content['attributes']['chartType'])


    elif content['tagName'] == 'card-module':
        if content['attributes']['type'] == 'read-more':
            pass
        else:
            logger.warning('unhandled card-module type ' + content['attributes']['type'])

    elif content['tagName'] == 'wildcard':
        if re.search(r'newsletter-widget|embed-form|opt-in-form', content['attributes']['url']):
            pass
        elif content['attributes'].get('altImage'):
            img_src = resize_image(content['attributes']['altImage']['url'])
            content_html += utils.add_image(img_src)
        elif content['attributes']['wildcard'].get('wildcardPromo') and re.search(r'art19|datawrapper|linkedin', content['attributes']['wildcard']['wildcardPromo']['cdata']):
            m = re.search(r'src="?([^"\s]+)', content['attributes']['wildcard']['wildcardPromo']['cdata'])
            content_html += utils.add_embed(m.group(1))
        else:
            logger.warning('unhandled wildcard content ' + content['attributes']['url'])

    elif content['tagName'] == 'content_embed':
        # Seems to be just related content
        pass

    elif content['tagName'] == 'group':
        for child in content['children']:
            content_html += render_content(child)

    elif content['tagName'] == 'post':
        content_html += '<hr/><h3 style="margin-bottom:0;">{}</h3>'.format(content['attributes']['title'])
        dt = datetime.fromisoformat(re.sub(r'\+(\d\d)(\d\d)$', r'+\1:\2', content['attributes']['dateLastPublished']))
        content_html += '<p style="margin-top:0">{}</p>'.format(utils.format_display_date(dt))
        for child in content['data']['body']['content']:
            content_html += render_content(child)

    else:
        logger.warning('unhandled content tagName ' + content['tagName'])

    return content_html


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', string=re.compile(r'window\.__s_data'))
    if not el:
        logger.warning('unable to find window.__s_data in ' + url)
        return None
    if save_debug:
        utils.write_file(el.string, './debug/debug.txt')
    m = re.search(r'window\.__s_data=(\{.+\});\s?window\.__c_data', el.string)
    if not m:
        logger.warning('unable to find json data in ' + url)
        return None
    data_json = json.loads(m.group(1))
    if save_debug:
        utils.write_file(data_json, './debug/debug.json')

    page_json = data_json['page']['page']
    item = {}
    item['id'] = page_json['id']
    item['url'] = page_json['url']
    item['title'] = page_json['headline']

    dt = datetime.fromisoformat(re.sub(r'\+(\d\d)(\d\d)$', r'+\1:\2', page_json['datePublished']))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(re.sub(r'\+(\d\d)(\d\d)$', r'+\1:\2', page_json['dateLastPublished']))
    item['date_modified'] = dt.isoformat()

    authors = []
    if page_json['authorFormatted'] != 'NA':
        for it in page_json['authorFormatted'].split('|'):
            authors.append(it.title())
    elif page_json.get('creatorOverwrite'):
        for it in page_json['creatorOverwrite'].split('|'):
            authors.append(it.title())
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
        if page_json.get('sourceOrganization') and not re.search(r'CNBC', page_json['sourceOrganization'][0]['tagName']):
            item['author']['name'] += ' ({})'.format(page_json['sourceOrganization'][0]['tagName'])

    item['tags'] = []
    for it in page_json['relatedTags']:
        item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    item['_image'] = page_json['promoImage']['url']
    item['summary'] = page_json['description']

    item['content_html'] = ''
    for layout in data_json['page']['page']['layout']:
        for column in layout['columns']:
            for module in column['modules']:
                if page_json['type'] == 'cnbcvideo':
                    if module['name'] == 'clipPlayer':
                        if module['data']['playbackURL'].startswith('https:'):
                            src = module['data']['playbackURL']
                        else:
                            src = 'https:' + module['data']['playbackURL']
                        item['content_html'] += utils.add_video(src, 'application/x-mpegURL', module['data']['image']['url'])
                        item['content_html'] += '<p>{}</p>'.format(module['data']['description'])

                elif page_json['type'] == 'live_story':
                    if module['name'] == 'featuredContent':
                        for content in module['data']['featuredContent']['content']:
                            item['content_html'] += render_content(content)
                    elif module['name'] == 'liveBlogBody':
                        for content in module['data']['body']['content']:
                            item['content_html'] += render_content(content)

                else:
                    if module['name'] == 'keyPoints':
                        for content in module['data']['keyPoints']:
                            item['content_html'] += render_content(content)
                    elif module['name'] == 'articleInlineMedia' and module['data'].get('featuredMedia'):
                        captions = []
                        if module['data']['featuredMedia'].get('caption'):
                            captions.append(module['data']['featuredMedia']['caption'])
                        if module['data']['featuredMedia'].get('copyrightHolder'):
                            captions.append(module['data']['featuredMedia']['copyrightHolder'])
                        img_src = resize_image(module['data']['featuredMedia']['url'])
                        item['content_html'] += utils.add_image(img_src, ' | '.join(captions))
                    elif module['name'] == 'articleBody':
                        if module['data']['body'].get('content'):
                            for content in module['data']['body']['content']:
                                item['content_html'] += render_content(content)
                        else:
                            if item.get('_image'):
                                item['content_html'] += utils.add_image(resize_image(item['_image']))
                            item['content_html'] += module['data']['articleBodyText']

    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://www.cnbc.com/rss-feeds/
    return rss.get_feed(url, args, site_json, save_debug, get_content)
