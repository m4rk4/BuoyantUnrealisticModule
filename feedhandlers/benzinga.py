import re
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_ticker_detail(symbols):
    api_url = 'https://data-api-next.benzinga.com/rest/v3/tickerDetail?apikey=81DC3A5A39D6D1A9D26FA6DF35A34&symbols=' + quote_plus(symbols)
    return utils.get_url_json(api_url)


def get_quote_delayed(symbols):
    api_url = 'https://data-api-next.benzinga.com/rest/v2/quoteDelayed?apikey=81DC3A5A39D6D1A9D26FA6DF35A34&symbols=' + quote_plus(symbols)
    return utils.get_url_json(api_url)


def get_crypto_quote(symbol):
    api_url = 'https://www.benzinga.com/lavapress/api/crypto/' + symbol
    return utils.get_url_json(api_url)


def format_block(block, quotes):
    block_html = ''
    if block['blockName'] == 'core/html':
        if block.get('tag'):
            if block['tag'] == 'link':
                return block_html
            elif block.get('tagAttributes') and block['tagAttributes'].get('className'):
                if 'wp-block-image' in block['tagAttributes']['className']:
                    m = re.search(r'srcset="([^"]+)', block['innerHTML'])
                    if m:
                        img_src = utils.image_from_srcset(m.group(1), 1200)
                    else:
                        m = re.search(r'src="([^"]+)', block['innerHTML'])
                        if m:
                            img_src = m.group(1)
                        else:
                            img_src = ''
                    if img_src:
                        m = re.search(r'href="([^"]+)', block['innerHTML'])
                        if m:
                            link = m.group(1)
                        else:
                            link = ''
                        # TODO: captions (figcaption?)
                        block_html = utils.add_image(img_src, link=link)
                        return block_html
                    else:
                        logger.warning('unhandled wp-block-image')
                elif 'wp-block-embed-twitter' in block['tagAttributes']['className']:
                    m = re.findall(r'href="([^"]+)', block['innerHTML'])
                    if m:
                        block_html += utils.add_embed(m[-1])
                        return block_html
                elif 'wp-block-embed-youtube' in block['tagAttributes']['className']:
                    m = re.search(r'src="([^"]+)', block['innerHTML'])
                    if m:
                        block_html += utils.add_embed(m.group(1))
                        return block_html
                elif block['tagAttributes']['className'] == 'ticker':
                    if block['tagAttributes'].get('data-ticker'):
                        symbol = block['tagAttributes']['data-ticker']
                    elif block['tagAttributes'].get('href'):
                        paths = list(filter(None, urlsplit(block['tagAttributes']['href']).path[1:].split('/')))
                        if 'stock' in paths or 'quote' in paths:
                            symbol = paths[-1]
                    else:
                        logger.warning('unknown ticker symbol ' + str(block['tagAttributes']))
                    if symbol:
                        q = None
                        if quotes and quotes.get(symbol):
                            q = quotes[symbol]
                        elif block['tagAttributes']['data-exchange'] == 'OTC':
                            otc_quotes = get_quote_delayed(symbol)
                            if otc_quotes and otc_quotes.get(symbol):
                                q = otc_quotes[symbol]
                        if q:
                            if q.get('lastTradePrice'):
                                price = ' ${:,.2f}'.format(q['lastTradePrice'])
                            elif q.get('previousClosePrice'):
                                price = ' ${:,.2f}'.format(q['previousClosePrice'])
                            else:
                                price = ''
                            if q.get('changePercent'):
                                if q['changePercent'] < 0:
                                    color = 'red'
                                    arrow = '▼'
                                else:
                                    color = 'green'
                                    arrow = '▲'
                                pct = ' {} {:,.2f}%'.format(arrow, q['changePercent'])
                            else:
                                color = 'gold'
                                pct = ''
                            block_html = '<a href="https://www.benzinga.com/quote/{}" style="color:{}; text-decoration:none;" target="_blank" title="{}">{}{}{}</a>'.format(q['symbol'], color, q['name'], q['symbol'], price, pct)
                            return block_html
                        elif block['tagAttributes']['data-exchange'] == 'CRYPTO':
                            q = get_crypto_quote(symbol.split('/')[0])
                            if q:
                                if q['price_change_percentage_24h'] < 0:
                                    color = 'red'
                                    arrow = '▼'
                                else:
                                    color = 'green'
                                    arrow = '▲'
                                block_html = '(<a href="https://www.benzinga.com/quote/{}-usd" style="color:{}; text-decoration:none;" target="_blank" title="{}">{} ${:,.2f} {} {:,.2f}%</a>)'.format(q['symbol'], color, q['name'], q['symbol'].upper(), q['current_price'], arrow, q['price_change_percentage_24h'])
                                return block_html
                        else:
                            logger.warning('unhandled ticker ' + symbol)
                elif 'wp-block-embed' in block['tagAttributes']['className']:
                    logger.warning('unhandled wp-block-embed class ' + block['tagAttributes']['className'])

            block_html += '<' + block['tag']
            if block.get('tagAttributes'):
                for key, val in block['tagAttributes'].items():
                    if key != 'className':
                        block_html += ' ' + key + '="' + val + '"'
            block_html += '>'
            if block['hasChild']:
                for child in block['childBlocks']:
                    block_html += format_block(child, quotes)
            if block['tag'] not in ['br', 'hr', 'img']:
                block_html += '</' + block['tag'] + '>'
        else:
            block_html += block['innerHTML']
    elif block['blockName'] == 'core/image':
        if block['tagAttributes'].get('alt') or block['tagAttributes'].get('width'):
            block_html += utils.add_image(block['tagAttributes']['src'])
        else:
            w, h = utils.get_image_size(block['tagAttributes']['src'])
            if (w and w == 1) or (h and h == 1):
                logger.debug('skipping image ' + block['tagAttributes']['src'])
            else:
                block_html += utils.add_image(block['tagAttributes']['src'])
    else:
        logger.warning('unhandled blockName ' + block['blockName'])

    if re.search(r'^<p>(<em>)?<strong>(<em>)?(Also Read:|Read Also:|See Also:)', block_html, flags=re.I):
        return ''
    return block_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if paths[-2].isnumeric():
        article_id = paths[-2]
    else:
        article_id = re.sub(r'^[a-z]+', '', paths[-2])
    api_url = 'https://www.benzinga.com/api/articles/{}/camel'.format(article_id)
    article_json = utils.get_url_json(api_url)
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['nodeId']
    item['url'] = article_json['metaProps']['canonical']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['createdAt'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('updatedAt'):
        dt = datetime.fromisoformat(article_json['updatedAt'])
        item['date_modified'] = dt.isoformat()

    item['author'] = {
        "name": article_json['metaProps']['author']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    item['tags'] = []
    if article_json.get('tags'):
        item['tags'] += [x['name'] for x in article_json['tags'] if x['name']]
    if article_json.get('terms'):
        item['tags'] += [x['name'] for x in article_json['terms'] if x['name']]
    if article_json.get('quotes'):
        item['tags'] += [x['name'] for x in article_json['quotes'] if x['name']]
        quotes = get_quote_delayed(','.join([x['symbol'] for x in article_json['quotes'] if x['symbol']]))
        if quotes and save_debug:
            utils.write_file(quotes, './debug/quotes.json')
    else:
        quotes = None
    if article_json.get('tickers'):
        item['tags'] += [x['name'] for x in article_json['tickers'] if x['name']]

    item['content_html'] = ''
    if article_json.get('primaryImage'):
        item['image'] = article_json['primaryImage']['url']
        item['content_html'] += utils.add_image(item['image'])
    elif article_json.get('image'):
        item['image'] = article_json['image']

    if article_json['metaProps'].get('description'):
        item['summary'] = article_json['metaProps']['description']
    elif article_json.get('teaserText'):
        item['summary'] = re.sub(r'^<p>|</p>$', '', article_json['teaserText'].strip())

    if article_json.get('keyItems'):
        if ''.join([x['value'] for x in article_json['keyItems']]):
            item['content_html'] += '<h3>Zinger Key Points</h3><ul>'
            for it in article_json['keyItems']:
                item['content_html'] += '<li>' + it['value'] + '</li>'
            item['content_html'] += '</ul><hr style="width:80%; margin:2em auto;">'

    # item['content_html'] += wp_posts.format_content(article_json['body'], item, site_json)
    for block in article_json['blocks']:
        item['content_html'] += format_block(block, quotes)

    if quotes:
        item['content_html'] += '<p><em>Stock prices as of ' + utils.format_display_date(datetime.now(timezone.utc)) + '</em></p>'
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    # http://feeds.benzinga.com/benzinga
    # https://www.benzinga.com/feeds/list
    if split_url.netloc == 'feeds.benzinga.com' or 'feed' in paths:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    feed_title = ''
    api_url = ''
    if 'quote' in paths:
        api_url = 'https://www.benzinga.com/api/news?tickers={}&excludeAutomated=true&limit=10&offset=0&type=story%2Cbenzinga_reach%2Cmarketbeat'.format(paths[1].upper())
        feed_title = paths[1].upper() + ' News | Benzinga'
    else:
        # Try 
        channels = utils.get_url_json('https://api.benzinga.com/api/v2/watchlists/channel')
        if channels:
            if save_debug:
                utils.write_file(channels, './debug/channels.json')
            channel = next((it for it in list(channels['data'].values()) if it['channel_path'] == split_url.path[1:]), None)
            if channel:
                api_url = 'https://www.benzinga.com/api/news?channels={}&displayOutput=abstract&limit=10&offset=0&type=benzinga_reach%2Cstory'.format('%2C'.join([x['tid'] for x in channel['tids']]))
                feed_title = channel['channel_name'] + ' | Benzinga'
    
    if not api_url:
        logger.warning('unhandled feed url ' + url)
        return None

    articles = utils.get_url_json(api_url)
    if not articles:
        return None
    if save_debug:
        utils.write_file(articles, './debug/feed.json')

    n = 0
    feed_items = []
    for article in articles:
        if save_debug:
            logger.debug('getting content for ' + article['url'])
        item = get_content(article['url'], args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
