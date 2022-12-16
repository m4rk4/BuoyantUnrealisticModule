import html, json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    return '{}://{}{}?w={}'.format(split_url.scheme, split_url.netloc, split_url.path, width)


def get_content(url, args, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    id = paths[-1].split('-')[-1]
    api_url = 'https://assets.msn.com/content/view/v2/Detail/{}/{}'.format(paths[0], id)
    article_json = utils.get_url_json(api_url)
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    #item['url'] = article_json['sourceHref']
    item['url'] = utils.clean_url(url)
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['publishedDateTime'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['updatedDateTime'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if article_json.get('authors'):
        authors = []
        for it in article_json['authors']:
            authors += re.split(r'\sand\s|,\s', it['name'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    if article_json.get('provider'):
        if item['author'].get('name'):
            item['author']['name'] += ' ({})'.format(article_json['provider']['name'])
        else:
            item['author']['name'] = article_json['provider']['name']

    item['tags'] = []
    if article_json.get('tags'):
        for it in article_json['tags']:
            if it['label'] not in item['tags']:
                item['tags'].append(it['label'])
    if article_json.get('keywords'):
        item['tags'] += article_json['keywords'].copy()
    if article_json.get('facets'):
        for it in article_json['facets']:
            if it['key'] == 'ProviderTags':
                item['tags'] += it['values'].copy()
    item['tags'] = list(set(item['tags']))
    if not item.get('tags'):
        del item['tags']

    if article_json.get('imageResources'):
        item['_image'] = article_json['imageResources'][0]['url']
    elif article_json.get('thumbnail'):
        item['_image'] = article_json['thumbnail']['image']['url']
    elif article_json.get('slides'):
        item['_image'] = article_json['slides'][0]['image']['url']

    if article_json.get('abstract'):
        item['summary'] = article_json['abstract']

    item['content_html'] = ''
    if article_json.get('videoMetadata'):
        if article_json.get('thumbnail'):
            poster = resize_image(article_json['thumbnail']['image']['url'])
        else:
            poster = ''
        video = next((it for it in article_json['videoMetadata']['externalVideoFiles'] if it['format'] == '1001'), None)
        if video:
            item['content_html'] = utils.add_video(video['url'], video['contentType'], poster, article_json.get('abstract'))
        else:
            logger.warning('unhandled videoMetadata in ' + item['url'])

    if article_json.get('body'):
        soup = BeautifulSoup(article_json['body'], 'lxml')
        for el in soup.find_all('img'):
            new_html = ''
            if el.get('data-document-id'):
                data_json = utils.get_url_json('https://assets.msn.com/breakingnews/v1/' + el['data-document-id'])
                if data_json:
                    if data_json['$type'] == 'image':
                        captions = []
                        if data_json.get('title'):
                            captions.append(data_json['title'])
                        if data_json.get('attribution'):
                            captions.append(data_json['attribution'])
                        new_html = utils.add_image(resize_image(data_json['href']), ' | '.join(captions))
                    elif data_json['$type'] == 'video':
                        if data_json.get('thumbnail'):
                            poster_json = utils.get_url_json('https://assets.msn.com/breakingnews/v1/' + data_json['thumbnail']['href'])
                            if poster_json:
                                poster = resize_image(poster_json['href'])
                            else:
                                poster = data_json['thumbnail']['sourceHref']
                        else:
                            poster = ''
                        video = next((it for it in data_json['videoFiles'] if it['format'] == '1001'), None)
                        if video:
                            video_src = video['href']
                            video_type = video['contentType']
                        else:
                            video_src = data_json['sourceHref']
                            if '.mp4' in video_src:
                                video_type = 'video/mp4'
                            else:
                                video_type = 'application/x-mpegURL'
                        new_html = utils.add_video(video_src, video_type, poster, data_json.get('caption'))
            if new_html:
                new_el = BeautifulSoup(new_html, 'lxml')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled img in ' + url)

        for el in soup.find_all(attrs={"data-embed-type": True}):
            new_html = ''
            if el['data-embed-type'] == 'social-auto':
                embed = next((it for it in article_json['socialEmbeds'] if it['id'] == el['data-embed-id']), None)
                if embed:
                    new_html = utils.add_embed(embed['postUrl'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'lxml')
                if el.parent and el.parent.name == 'div':
                    el.parent.insert_after(new_el)
                    el.parent.decompose()
                else:
                    el.insert_after(new_el)
                    el.decompose()
            else:
                logger.warning('unhandled data-embed-type {} in {}'.format(el['data-embed-type'], url))

        item['content_html'] += str(soup)

    if article_json.get('slides'):
        for it in article_json['slides']:
            desc = ''
            if it.get('title'):
                desc += '<h4>{}</h4>'.format(it['title'])
            if it.get('body'):
                desc += it['body']
            item['content_html'] += utils.add_image(resize_image(it['image']['url']), it['image'].get('attribution'), desc=desc)

    item['content_html'] = re.sub(r'</(div|figure|table)>\s*<(div|figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_card_item(url, args, save_debug):
    if save_debug:
        logger.debug('getting content for ' + url)
    item = get_content(url, args, save_debug)
    if item:
        if utils.filter_item(item, args) == True:
            return item
    return None


def get_feed(args, save_debug=False):
    page_html = utils.get_url_html(args['url'])
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('head', attrs={"data-client-settings": True})
    if not el:
        logger.warning('unable to determine data-client-settings in ' + args['url'])
    client_settings = json.loads(html.unescape(el['data-client-settings']))
    if save_debug:
        utils.write_file(client_settings, './debug/settings.json')
    config_url = 'https://www.msn.com{}/{}/config/?expType=AppConfig&expInstance=default&apptype={}&v={}&targetScope='.format(client_settings['servicesEndpoints']['crs']['path'], client_settings['servicesEndpoints']['crs']['v'], client_settings['apptype'], client_settings['bundleInfo']['v'])
    target_scope = {
        "audienceMode": "adult",
        "browser": client_settings['browser'],
        "deviceFormFactor": client_settings['deviceFormFactor'],
        "domain": client_settings['domain'],
        "locale": client_settings['locale'],
        "os": client_settings['os'],
        "platform": "web",
        "pageType": client_settings['pagetype'],
        "pageExperiments": [
            "prg-1s-boostcoach", "prg-1s-p2boostads", "prg-1s-vlprecalllog2",
            "prg-1s-whp-sport", "prg-1sw-11refre", "prg-1sw-2cmoney", "prg-1sw-aqhfc",
            "prg-1sw-aqnew", "prg-1sw-bnpttcg1", "prg-1sw-cbm0", "prg-1sw-cinlnftch",
            "prg-1sw-crfy22c", "prg-1sw-crprepwl", "prg-1sw-dcwxcf", "prg-1sw-ebrfnt3",
            "prg-1sw-enablenpq", "prg-1sw-esp", "prg-1sw-eup2", "prg-1sw-fwc", "prg-1sw-fwc",
            "prg-1sw-fwc", "prg-1sw-fwcntp", "prg-1sw-fwcp1", "prg-1sw-fwcp2",
            "prg-1sw-gempcv5p8", "prg-1sw-ip2msfeamkc", "prg-1sw-multif1", "prg-1sw-multif2",
            "prg-1sw-multifn", "prg-1sw-nearss", "prg-1sw-ntpxap", "prg-1sw-p1wtrclm",
            "prg-1sw-p2video", "prg-1sw-pde0", "prg-1sw-remvtfi", "prg-1sw-rhani",
            "prg-1sw-saclfen1c", "prg-1sw-saecmig4", "prg-1sw-sagefreroc",
            "prg-1sw-sagfswingt22", "prg-1sw-sbn-mm", "prg-1sw-secbadge", "prg-1sw-ski1",
            "prg-1sw-sptprvmax5", "prg-1sw-tbrcounter", "prg-1sw-ulce1", "prg-1sw-wcf1",
            "prg-1sw-wcf2", "prg-1sw-wcfnt", "prg-1sw-wcsfrwma", "prg-1sw-wcstart",
            "prg-1sw-wxhf-ht-ct", "prg-1sw-wxtsetr9", "prg-2sw-esprtcsp", "prg-ads-ip11c",
            "prg-adspeek", "prg-boostcoach", "prg-cookiecont", "prg-e-whp-sport-r",
            "prg-feed2p2-t1", "prg-gridbyregion", "prg-hprewflyout-t", "prg-ias",
            "prg-live-crd2", "prg-minusfdhead", "prg-nlclose", "prg-ntbl-cmhpc",
            "prg-p2-pinsame1", "prg-pr2-boostr3c", "prg-pr2-casl-c", "prg-pr2-csgm4-c",
            "prg-pr2-csgm4e-c", "prg-pr2-csv2", "prg-pr2-csv2t", "prg-pr2-lfnoph",
            "prg-pr2-pvcold", "prg-pr2-telpin", "prg-prong2-boost2c", "prg-sc-prong2",
            "prg-sh-automo7", "prg-sh-caka", "prg-sh-mbcfrp", "prg-sh-nl-ctrl",
            "prg-sh-xpayv2", "prg-spr-t-d3at35", "prg-ugc-proforma", "prg-ugc-test-3",
            "prg-upsaip-r-t", "prg-upsaip-w1-t", "prg-useplmtmgr", "prg-videoimp0s",
            "prg-wea-allxap", "prg-wea-subxap", "prg-weanouser1", "prg-wpo-pnpc",
            "prg-wpo-sagernk", "prg-wpo-tscgct", "prg-wscards-t1", "prg-wx-anmpr",
            "prg-wx-aqnew", "prg-wx-aqzoom", "prg-wx-auto3d1", "prg-wx-morci",
            "prg-wx-morl1ci", "prg-wx-sbn-vm"
        ]
    }
    if client_settings.get('ocid'):
        target_scope['ocid'] = client_settings['ocid']
    config_url += json.dumps(target_scope).replace(' ', '').replace('"', '%22')
    config_json = utils.get_url_json(config_url)
    if not config_json:
        logger.warning('unable to get AppConfig for ' + args['url'])
        return None
    if save_debug:
        utils.write_file(config_json, './debug/config.json')

    # https://assets.msn.com/bundles/v1/hub/latest/common.701d10a50cf16e1df0da.js
    # function getOneServiceApiKey
    api_key = '0QfOX3Vn51YCzitbLaRkTTBadtWpgTN8NZLW0C1SEM'

    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) > 0 and paths[1] == 'sports':
        if paths[-1] == 'sports':
            sport = 'default'
        elif paths[-1] == 'ncaafb':
            sport = 'collegefootball'
        elif paths[-1] == 'ncaabk':
            sport = 'collegebasketball'
        elif paths[-1] == 'ncaawbk':
            sport = 'wcbk'
        elif 'soccer' in paths:
            if paths[-1] == 'soccer':
                sport = 'soccer'
            elif paths[-1] == 'mls':
                sport = 'usamajorleaguesoccer'
            elif paths[-1] == 'fifa-world-cup':
                sport = 'internationalworldcup'
            elif paths[-1] == 'nwsl':
                sport = 'usanationalwomenssoccerleague'
            elif paths[-1] == 'uefa-champions-league':
                sport = 'internationalclubsuefachampionsleague'
            elif paths[-1] == 'premier-league':
                sport = 'englandpremierleague'
            elif paths[-1] == 'ligue-un':
                sport = 'franceligue1'
            elif paths[-1] == 'la-liga':
                sport = 'spainlaliga'
            elif paths[-1] == 'bundesliga':
                sport = 'germanybundesliga'
            elif paths[-1] == 'serie-a':
                sport = 'italyseriea'
            elif paths[-1] == 'uefa-europa-league':
                sport = 'uefaeuropaleague'
            elif paths[-1] == 'europa-conference-league':
                sport = 'soccer'
            elif paths[-1] == 'wc-concacaf-qualifiers':
                sport = 'internationalworldcupqualificationconcacaf'
            elif paths[-1] == 'concacaf-champions-league':
                sport = 'internationalclubsconcacafchampionsleague'
            elif paths[-1] == 'coppa-italia':
                sport = 'italycoppaitalia'
            elif paths[-1] == 'brasileirao-serie-a':
                sport = 'brazilbrasileiroseriea'
        elif 'cricket' in paths:
            if paths[-1] == 'cricket':
                sport = 'cricket'
            elif paths[-1] == 't20wc':
                sport = 'ICCWorldTwenty20'
            elif paths[-1] == 'cricket-internationals':
                sport = 'cricket'
            elif paths[-1] == 'bbl':
                sport = 'bigbashleaguet20'
            elif paths[-1] == 'lpl':
                sport = 'lankapremierleaguet20'
            elif paths[-1] == 'supersmasht20':
                sport = 'supersmasht20'
            elif paths[-1] == 'sa20':
                sport = 'cricket'
        elif 'motorsports' in paths:
            if paths[-1] == 'motorsports':
                sport = 'racing'
            elif paths[-1] == 'nascar-two':
                sport = 'nascar2'
            else:
                sport = paths[-1]
                # TODO: indycar and moto-gp use different page format - need to scrape the links from the page
        else:
            sport = paths[-1]

        feed_id = next((it['feedId'] for it in config_json['configs']['SportsPage/default']['properties']['superFeedIds'] if (it.get('league') == sport or it.get('sport') == sport)), None)
        if not feed_id:
            logger.warning('unknown feedId for ' + args['url'])
            return None
        card_config = config_json['configs']['GridViewFeed/default']['properties']['riverSectionCardProviderConfig']['initialRequest']
        feed_url = 'https://assets.msn.com/service/MSN/Feed?$top={}&DisableTypeSerialization=true&apikey={}&cipenabled={}&cm=en-us&ids={}&location=40.7484|-73.9846&infopaneCount={}&ocid={}&queryType=myfeed&responseSchema=cardview&timeOut={}&wrapodata=false'.format(
            24,
            card_config['apiKey'],
            'false',
            feed_id,
            card_config['infopaneCount'],
            card_config['ocid'],
            card_config['timeoutMs'])
    else:
        for key, val in config_json['configs'].items():
            if key.startswith('River/index_hub_unique') or key.startswith('StripeFeed/default'):
                card_config = val['properties']['cardProviderConfig']['initialRequest']
                feed_url = 'https://assets.msn.com/service/MSN/Feed?$top={}&DisableTypeSerialization=true&apikey={}&cipenabled={}&cm=en-us&ids={}&location=40.7484|-73.9846&infopaneCount={}&ocid={}&queryType=myfeed&responseSchema=cardview&timeOut={}&wrapodata=false'.format(
                    card_config['count'],
                    api_key,
                    str(card_config['complexInfopaneEnabled']),
                    card_config['feedId'],
                    card_config['infopaneItemCount'],
                    card_config['ocid'],
                    card_config['timeoutMs'])
            elif key.startswith('StripeView/default'):
                for k, v in val['properties']['staticStripeExperiences'].items():
                    if v.get('feedId'):
                        if config_json['configs'].get('StripeFeed/' + v['configRef']['instanceSrc']):
                            card_config = config_json['configs']['StripeFeed/' + v['configRef']['instanceSrc']]['properties']['cardProviderConfig']['initialRequest']
                            feed_url = 'https://assets.msn.com/service/MSN/Feed?$top={}&DisableTypeSerialization=true&apikey={}&cipenabled={}&cm=en-us&ids={}&location=40.7484|-73.9846&infopaneCount={}&ocid={}&queryType=myfeed&responseSchema=cardview&timeOut={}&wrapodata=false'.format(
                                card_config['count'],
                                api_key,
                                str(card_config['complexInfopaneEnabled']),
                                v['feedId'],
                                card_config['infopaneItemCount'],
                                card_config['ocid'],
                                card_config['timeoutMs'])

    if not feed_url:
        logger.warning('unhandled page feed in ' + args['url'])
        return None

    urls = []
    feed_json = utils.get_url_json(feed_url)
    if not feed_json:
        return None
    if save_debug:
        utils.write_file(feed_json, './debug/feed.json')

    for card in feed_json['subCards']:
        if card['type'] == 'infopane':
            for subcard in card['subCards']:
                urls.append(subcard['url'])
        else:
            urls.append(card['url'])

    feed_items = []
    for url in urls:
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)

    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
