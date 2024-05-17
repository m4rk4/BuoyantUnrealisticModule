import json, math, pygal, pytz, re
from bs4 import BeautifulSoup, Comment
from datetime import datetime
from pygal.style import Style
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import dirt, rss

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
    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    # print(next_url)
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


def make_stock_chart(symbol):
    data_json = utils.get_url_json('https://sherwood.news/api/public/fetch_historical/?symbol={}&interval=5minute&span=day'.format(symbol))
    if not data_json:
        return ''

    x = []
    y = []
    for pt in data_json['historicals']:
        dt = datetime.fromisoformat(pt['begins_at']).astimezone(pytz.timezone(config.local_tz))
        x.append(dt)
        y.append(float(pt['close_price']))

    prev_price = float(data_json['previous_close_price'])
    curr_price = float(data_json['historicals'][-1]['close_price'])
    diff = 100 * (curr_price - prev_price) / prev_price
    title = '{}: ${:.2f} '.format(symbol, curr_price)
    if diff < 0:
        title += ' (▼ {:.2f}%)'.format(diff)
    else:
        title += ' (▲ {:.2f}%)'.format(diff)

    custom_style = Style(
        background='transparent',
        plot_background='transparent',
        title_font_size=24,
        major_label_font_size=16,
        label_font_size=16
    )
    n = math.ceil(len(x) / 10)
    line_chart = pygal.Line(x_labels_major_every=n, show_minor_x_labels=False, truncate_label=-1, style=custom_style)
    line_chart.title = title
    line_chart.x_title = utils.format_display_date(x[-1], False)
    line_chart.x_labels = map(lambda dt: dt.strftime('%H:%M'), x)
    line_chart.y_title = 'Price ($)'
    line_chart.add(data_json['symbol'], y)
    chart_svg = line_chart.render(is_unicode=True)

    caption = '<a href="https://robinhood.com/us/en/stocks/{0}/">{0}</a>: updated {1}'.format(symbol, utils.format_display_date(x[-1]))
    chart_html = '<figure style="margin:0; padding:0;">' + chart_svg + '<figcaption><small>' + caption + '</small></figcaption></figure>'
    return chart_html


def render_content(node):
    content_html = ''
    if node['nodeType'] == 'embedded-entry-block':
        if node['data']['target']['sys']['contentType']['sys']['id'] == 'assetStockChart':
            content_html += make_stock_chart(node['data']['target']['fields']['symbol'])
        else:
            logger.warning('unhandled embedded-entry-block type ' + node['data']['target']['sys']['contentType']['sys']['id'])
    else:
        content_html += dirt.render_content(node, None)
    return content_html


def get_post_content(post, url, args, save_debug):
    item = get_article_content(post['fields']['article'], url, args, save_debug)

    item['id'] = post['sys']['id']
    # item['id'] = article['sys']['id']

    item['url'] = 'https://sherwood.news/{}/{}/'.format(post['fields']['primaryCategory']['fields']['slug'], post['fields']['slug'])

    if post['fields'].get('siteHed') and len(post['fields']['siteHed'].strip()) > 0:
        item['title'] = post['fields']['siteHed']
    else:
        item['title'] = post['fields']['hed']

    if post['fields'].get('authors'):
        authors = []
        for it in post['fields']['authors']:
            authors.append(it['fields']['name'])
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if post['fields'].get('dek'):
        if not item.get('summary'):
            item['summary'] = post['fields']['dek']
        item['content_html'] = '<p><em>' + post['fields']['dek'] + '</em></p>' + item['content_html']

    return item


def get_article_content(article, url, args, save_debug):
    item = {}
    item['id'] = article['sys']['id']
    item['url'] = url

    if article['fields'].get('title'):
        item['title'] = article['fields']['title']

    dt = datetime.fromisoformat(article['sys']['createdAt'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article['sys'].get('updatedAt'):
        dt = datetime.fromisoformat(article['sys']['updatedAt'])
        item['date_modified'] = dt.isoformat()

    if article['fields'].get('author'):
        item['author'] = {"name": article['fields']['author']['fields']['name']}

    if article['metadata'].get('tags'):
        item['tags'] = []
        for it in article['metadata']['tags']:
            if it['sys']['type'] == 'Link' and it['sys']['linkType'] == 'Tag':
                item['tags'].append(it['sys']['id'])

    item['content_html'] = ''

    if article['fields'].get('siteImage') and article['fields']['siteImage'].get('fields'):
        item['_image'] = 'https:' + article['fields']['siteImage']['fields']['file']['url']
        item['content_html'] += utils.add_image(item['_image'], article['fields']['siteImage']['fields'].get('description'))
    elif article['fields'].get('quickPostSourceMedia') and article['fields'][
        'quickPostSourceMedia'].get('fields'):
        item['_image'] = 'https:' + article['fields']['quickPostSourceMedia']['fields']['file']['url']
        item['content_html'] += utils.add_image(item['_image'], article['fields']['quickPostSourceMedia']['fields'].get('description'))
    elif article['fields'].get('image') and article['fields']['image'].get('fields'):
        item['_image'] = 'https:' + article['fields']['image']['fields']['file']['url']
        # item['content_html'] += utils.add_image(item['_image'], article['fields']['image']['fields'].get('description'))

    if article['fields'].get('dropCap'):
        dropcap = article['fields']['dropCap']
    else:
        dropcap = False

    if article['fields'].get('bodyContent') and article['fields']['bodyContent'].get('content'):
        for content in article['fields']['bodyContent']['content']:
            content_html = render_content(content)
            if dropcap and content_html.startswith('<p>'):
                content_html = re.sub(r'^(<.+?>)(["“]?\w)', r'\1<span style="float:left; font-size:4em; line-height:0.8em;">\2</span>', content_html, 1)
                content_html += '<span style="clear:left;"></span>'
                dropcap = False
            item['content_html'] += content_html

    if article['fields'].get('bodyContentAboveTheFold') and article['fields']['bodyContentAboveTheFold'].get('content'):
        for content in article['fields']['bodyContentAboveTheFold']['content']:
            item['content_html'] += render_content(content)

    if article['fields'].get('contentRichText') and article['fields']['contentRichText'].get('content'):
        for content in article['fields']['contentRichText']['content']:
            item['content_html'] += render_content(content)

    if article['fields'].get('takeawayContentRichText') and article['fields']['takeawayContentRichText'].get('content'):
        item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;">The Takeaway:</div>'
        for content in article['fields']['contentRichText']['content']:
            item['content_html'] += render_content(content)

    if article['fields'].get('items'):
        for asset in article['fields']['items']['fields']['assets']:
            if asset['sys']['contentType']['sys']['id'] == 'assetMedia':
                img_src = 'https:' + asset['fields']['media']['fields']['file']['url']
                item['content_html'] += utils.add_image(img_src, asset['fields']['media']['fields'].get('description'))
            elif asset['sys']['contentType']['sys']['id'] == 'assetStockChart':
                item['content_html'] += make_stock_chart(asset['fields']['symbol'])
            # elif asset['sys']['contentType']['sys']['id'] == 'assetDataPost':

            else:
                logger.warning('unhandled asset content type {} in {}'.format(asset['sys']['contentType']['sys']['id'], url))

    if article['fields'].get('quickPostSource'):
        post_source = utils.add_embed(article['fields']['quickPostSource'])
        if post_source:
            item['content_html'] += '<h2>Source:</h2>' + post_source

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_newsletter_content(newsletter, url, args, save_debug):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    item = {}
    item['id'] = newsletter['sys']['id']
    item['url'] = 'https://sherwood.news/{}/newsletters/{}'.format(paths[0], newsletter['fields']['slug'])
    item['title'] = newsletter['fields']['title']

    dt = datetime.fromisoformat(newsletter['fields']['publishedAt'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": "Sherwood News"}

    item['content_html'] = ''
    if newsletter['fields'].get('openingMedia') and newsletter['fields']['openingMedia'].get('fields'):
        item['_image'] = 'https:' + newsletter['fields']['openingMedia']['fields']['file']['url']
        item['content_html'] += utils.add_image(item['_image'], newsletter['fields']['openingMedia']['fields'].get('description'))

    if newsletter['fields'].get('openingWordsRichText') and newsletter['fields']['openingWordsRichText'].get('content'):
        for content in newsletter['fields']['openingWordsRichText']['content']:
            item['content_html'] += render_content(content)

    for section in newsletter['fields']['sections']:
        if section['sys']['contentType']['sys']['id'] == 'promotionArticle':
            continue
        item['content_html'] += '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
        if section['fields'].get('slug'):
            link = 'https://sherwood.news/{}/{}/{}'.format(paths[0], section['fields']['vertical']['fields']['slug'], section['fields']['slug'])
            item['content_html'] += '<div style="font-size:1.2em; font-weight:bold;"><a href="{}">{}</a></div>'.format(
                link, section['fields']['title'])
        elif section['fields'].get('url'):
            item['content_html'] += '<div style="font-size:1.2em; font-weight:bold;"><a href="{}">{}</a></div>'.format(
                section['fields']['url'], section['fields']['title'])
        else:
            item['content_html'] += '<div style="font-size:1.2em; font-weight:bold;">{}</div>'.format(
                section['fields']['title'])
        if section['fields'].get('author'):
            item['content_html'] += 'By ' + section['fields']['author']['fields']['name']
        # image?
        if section['fields'].get('contentRichText') and section['fields']['contentRichText'].get('content'):
            for content in section['fields']['contentRichText']['content']:
                item['content_html'] += render_content(content)
        if section['fields'].get('takeawayContentRichText') and section['fields']['takeawayContentRichText'].get('content'):
            item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;">The Takeaway:</div>'
            for content in section['fields']['takeawayContentRichText']['content']:
                item['content_html'] += render_content(content)
        if section['fields'].get('body') and section['fields']['body'].get('content'):
            for content in section['fields']['body']['content']:
                item['content_html'] += render_content(content)
        if section['fields'].get('fact') and section['fields']['fact'].get('content'):
            for content in section['fields']['fact']['content']:
                item['content_html'] += render_content(content)
    return item

def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')
    if next_data['pageProps'].get('post'):
        return get_post_content(next_data['pageProps']['post'], url, args, save_debug)
    elif next_data['pageProps'].get('article'):
        return get_article_content(next_data['pageProps']['article'], url, args, save_debug)
    elif next_data['pageProps'].get('newsletter'):
        return get_newsletter_content(next_data['pageProps']['newsletter'], url, args, save_debug)
    return None
