import base64, json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import unquote_plus, urlsplit

import config, utils
from feedhandlers import brightcove

import logging

logger = logging.getLogger(__name__)


def get_window_state(url, window_state):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    page_soup = BeautifulSoup(page_html, 'lxml')
    el = page_soup.find('script', string=re.compile(r'window\.__{}__'.format(window_state)))
    if not el:
        logger.warning('unable to find window.__{}__ in {}'.format(window_state, url))
        return None
    i = el.string.find('{')
    j = el.string.rfind('}') + 1
    return json.loads(el.string[i:j])


def get_content(url, args, site_json, save_debug=False):
    apollo_state = get_window_state(url, 'APOLLO_STATE')
    if not apollo_state:
        return None
    if save_debug:
        utils.write_file(apollo_state, './debug/debug.json')

    article_json = None
    for key, val in apollo_state['ROOT_QUERY'].items():
        if key.startswith('article'):
            article_json = apollo_state[val['id']]
            break
    if not article_json:
        logger.warning('unknown article in ' + url)
        return None

    item = {}
    item['id'] = article_json['id']
    item['url'] = 'https://' + urlsplit(url).netloc + article_json['categoryPath']
    item['title'] = article_json['headline']

    dt = datetime.fromisoformat(article_json['publishedTime'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['updatedTime'])
    item['date_modified'] = dt.isoformat()

    item['authors'] = []
    for it in article_json['bylines']:
        byline = apollo_state[it['id']]
        if 'author' in byline:
            author = apollo_state[byline['author']['id']]
            item['authors'].append({"name": author['name']})
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = []
    if article_json.get('label'):
        item['tags'].append(article_json['label'])
    for key, val in article_json.items():
        if key.startswith('topics') and val:
            for it in val:
                topic = apollo_state[it['id']]
                item['tags'].append(topic['name'])

    if article_json.get('seoDescription'):
        item['summary'] = article_json['seoDescription']

    item['content_html'] = ''
    if article_json.get('standfirst'):
        item['content_html'] += '<p><em>' + article_json['standfirst'] + '</em></p>'

    if article_json.get('leadAsset'):
        asset = apollo_state[article_json['leadAsset']['id']]
        if asset['__typename'] == 'Image':
            captions = []
            if asset.get('caption'):
                captions.append(asset['caption'])
            if asset.get('credits'):
                captions.append(asset['credits'])
            img_src = ''
            for key, val in asset.items():
                if key.startswith('crop') and '16:9' in key:
                    crop = apollo_state[val['id']]
                    img_src = crop['url']
                    break
            if img_src:
                item['image'] = img_src
                item['content_html'] += utils.add_image(img_src, ' | '.join(captions))
            else:
                logger.warning('unhandled leadAsset img_src in ' + item['url'])
        else:
            logger.warning('unhandled leadAsset type {} in {}'.format(asset['__typename'], item['url']))

    def format_content(content):
        content_html = ''
        if content['name'] == 'text':
            content_html = content['attributes']['value']
        elif content['name'] == 'paragraph':
            content_html = '<p>'
            for child in content['children']:
                content_html += format_content(child)
            content_html += '</p>'
        elif content['name'] == 'paywall':
            for child in content['children']:
                content_html += format_content(child)
        elif content['name'] == 'link':
            content_html = '<a href="{}" target="_blank">'.format(content['attributes']['href'])
            for child in content['children']:
                content_html += format_content(child)
            content_html += '</a>'
        elif content['name'].startswith('heading'):
            content_html = '<h{}>'.format(content['name'][-1])
            for child in content['children']:
                content_html += format_content(child)
            content_html += '</h{}>'.format(content['name'][-1])
        elif content['name'] == 'bold':
            content_html = '<strong>'
            for child in content['children']:
                content_html += format_content(child)
            content_html += '</strong>'
        elif content['name'] == 'italic':
            content_html = '<em>'
            for child in content['children']:
                content_html += format_content(child)
            content_html += '</em>'
        elif content['name'] == 'unorderedList':
            content_html = '<ul>'
            for child in content['children']:
                content_html += format_content(child)
            content_html += '</ul>'
        elif content['name'] == 'orderedList':
            content_html = '<ol>'
            for child in content['children']:
                content_html += format_content(child)
            content_html += '</ol>'
        elif content['name'] == 'listElement':
            content_html = '<li>'
            for child in content['children']:
                content_html += format_content(child)
            content_html += '</li>'
        elif content['name'] == 'image':
            captions = []
            if content['attributes'].get('caption'):
                captions.append(content['attributes']['caption'])
            if content['attributes'].get('credits'):
                captions.append(content['attributes']['credits'])
            content_html = utils.add_image(content['attributes']['url'], ' | '.join(captions))
        elif content['name'] == 'video':
            if content['attributes'].get('brightcoveVideoId'):
                bc_args = {
                    "data-key": content['attributes']['brightcovePolicyKey'],
                    "data-account": content['attributes']['brightcoveAccountId'],
                    "data-video-id": content['attributes']['brightcoveVideoId'],
                    "caption": content['attributes'].get('caption'),
                    "embed": True
                }
                bc_item = brightcove.get_content('', bc_args, {"module": "brightcove"}, False)
                if bc_item:
                    content_html = bc_item['content_html']
            else:
                logger.warning('unhandled video content')
        elif content['name'] == 'break':
            content_html = '<br/>'
        elif content['name'] == 'keyFacts':
            if content['attributes']['title'] != 'Read more':
                content_html += '<blockquote style="border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;"><h3>' + content['attributes']['title'] + '</h3>'
                for child in content['children']:
                    content_html += format_content(child)
                content_html += '</blockquote>'
        elif content['name'] == 'interactive':
            if content['attributes']['element']['value'] == 'twitter-embed':
                content_html = utils.add_embed(content['attributes']['element']['attributes']['url'])
            elif content['attributes']['element']['value'] == 'times-embed-iframe-max':
                content_html = utils.add_embed(content['attributes']['element']['attributes']['src'])
            elif content['attributes']['element']['value'] == 'times-datawrapper':
                content_html = utils.add_embed(unquote_plus(content['attributes']['element']['attributes']['embed-code']))
            elif content['attributes']['element']['value'] == 'responsive-graphics':
                deck = utils.get_url_json('https://gobble.timesdev.tools/deck/api/deck-post-action/' + content['attributes']['element']['attributes']['deck-id'])
                if deck and deck['body'].get('data'):
                    images = []
                    for it in deck['body']['data']:
                        if it['type'] == 'image':
                            images.append(it['data'])
                    if images:
                        image = utils.closest_dict(images, 'Size', 10000)
                        content_html = utils.add_image(image['Image'], deck['deck_name'], link=image['Image'])
                if not content_html:
                    logger.warning('unhandled responsive-graphics interactive')
            elif content['attributes']['element']['value'] == 'opta-cricket-scorecard':
                content_html = add_opta_cricket_scorecard(content['attributes']['element']['attributes']['match'])
            elif content['attributes']['element']['value'] == 'opta-rugby-union-match-summary-v2':
                content_html = add_opta_rugby_summary(content['attributes']['element']['attributes']['match'], False)
            elif content['attributes']['element']['value'] == 'opta-rugby-union-match-stats-v2':
                content_html = add_opta_rugby_summary(content['attributes']['element']['attributes']['match'], True)
            elif content['attributes']['element']['value'] == 'opta-rugby-union-standings-v2':
                content_html = add_opta_rugby_standings(content['attributes']['element']['attributes']['competition'], content['attributes']['element']['attributes']['season'])
            elif content['attributes']['element']['value'] == 'article-header':
                content_html += '<div>&nbsp;</div><hr/>'
                if content['attributes']['element']['attributes'].get('updated'):
                    dt = datetime.fromisoformat(content['attributes']['element']['attributes']['updated'])
                    content_html += '<div style="font-size:0.8em;">' + utils.format_display_date(dt) + '</div>'
                content_html += '<div style="font-size:1.2em; font-weight:bold;">' + content['attributes']['element']['attributes']['headline'] + '</div>'
            elif content['attributes']['element']['value'] == 'newsletter-puff':
                pass
            else:
                logger.warning('unhandled interactive content ' + content['attributes']['element']['value'])
        elif content['name'] == 'ad' or content['name'].startswith('inlineAd'):
            pass
        else:
            logger.warning('unhandled content name ' + content['name'])
        return content_html

    for content in article_json['paywalledContent']['json']:
        item['content_html'] += format_content(content)

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def add_opta_rugby_standings(competition, season_id):
    user = 'OW2017'
    psw = 'dXWg5gVZ'
    url = 'https://omo.akamai.opta.net/auth/competition.php?feed_type=ru2&competition={0}&season_id={1}&user={2}&psw={3}&jsoncallback=ru2_{0}_{1}'.format(competition, season_id, user, psw)
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "referer": "https://www.thetimes.com/",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"129\", \"Not=A?Brand\";v=\"8\", \"Chromium\";v=\"129\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "script",
        "sec-fetch-mode": "no-cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0"
    }
    callback = utils.get_url_html(url, headers=headers)
    if not callback:
        return ''
    i = callback.find('{')
    j = callback.rfind('}') + 1
    competition_json = json.loads(callback[i:j])
    comp = competition_json['table']['comp']
    utils.write_file(competition_json, './debug/competition.json')
    standings = '<table style="width:90%; margin:auto; padding:8px; text-align:center; border:1px solid #444; border-radius:10px;">'
    standings += '<tr><td colspan="9" style="font-size:1.05em; font-weight:bold;">Standings: {}</td></tr>'.format(comp['group']['@attributes']['name'])
    standings += '<tr><td>Pos.</td><td></td><td></td><td>P</td><td>W</td><td>D</td><td>L</td><td>+/-</td><td>PTS</td></tr>'
    for i, team in enumerate(comp['group']['team']):
        standings += '<tr><td>{}</td><td><img src="https://omo.akamai.opta.net/image.php?secure=true&h=omo.akamai.opta.net&sport=rugby&entity=team&description=badges&dimensions=20&id={}"/></td><td style="text-align:left;">{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(i + 1, team['@attributes']['id'], team['@attributes']['name'], team['@attributes']['played'], team['@attributes']['won'], team['@attributes']['drawn'], team['@attributes']['lost'], team['@attributes']['pointsdiff'], team['@attributes']['points'])
    standings += '</table>'
    return standings


def add_opta_football_summary(game_id, add_stats=False):
    # https://www.thetimes.com/sport/football/article/finland-england-nations-league-score-result-table-hj0n8mtrk
    # user and password are found in https://secure.widget.cloud.opta.net/v3/v3.opta-widgets.js
    # m = re.search(r'this\.omo_username="([^"]+)"', widget_html)
    # m = re.search(r'this\.omo_password="([^"]+)"', widget_html)
    user = 'OW2017'
    psw = 'dXWg5gVZ'
    # url = 'https://omo.akamai.opta.net/auth/?feed_type=f9_packed&game_id={0}&user={1}&psw={2}&jsoncallback=f9_packed_{0}'.format(game_id, user, psw)
    url = 'https://omo.akamai.opta.net/auth/?feed_type=f9_packed&game_id={0}&user={1}&psw={2}'.format(game_id, user, psw)
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "referer": "https://www.thetimes.com/",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"129\", \"Not=A?Brand\";v=\"8\", \"Chromium\";v=\"129\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "script",
        "sec-fetch-mode": "no-cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0"
    }
    # callback = utils.get_url_html(url, headers=headers)
    # if not callback:
    #     return ''
    # i = callback.find('{')
    # j = callback.rfind('}') + 1
    # game_json = json.loads(callback[i:j])
    game_json = utils.get_url_json(url)
    utils.write_file(game_json, './debug/game.json')
    # TODO: how to decode game_json['data']
    # See https://secure.widget.cloud.opta.net/v3/v3.opta-widgets.js
    # u = atob(n.data)
    data = base64.b64decode(game_json['data'])
    # e.teajs.decrypt(u, "P!Fgob$*LKDF D)(F IDD&P?/")
    # key is supposed to be 16 bytes??
    key = "P!Fgob$*LKDF D)(F IDD&P?/"
    # Python TEA decryptors don't work

    # Football standings
    # https://omo.akamai.opta.net/auth/competition.php?feed_type=f3_packed&competition=941&season_id=2024&user=OW2017&psw=dXWg5gVZ&jsoncallback=f3_packed_941_2024
    return ''


def add_opta_rugby_summary(game_id, add_stats=False):
    # user and password are found in https://secure.widget.cloud.opta.net/v3/v3.opta-widgets.js
    # m = re.search(r'this\.omo_username="([^"]+)"', widget_html)
    # m = re.search(r'this\.omo_password="([^"]+)"', widget_html)
    user = 'OW2017'
    psw = 'dXWg5gVZ'
    url = 'https://omo.akamai.opta.net/auth/?feed_type=ru7&game_id={0}&user={1}&psw={2}&jsoncallback=ru7_{0}'.format(game_id, user, psw)
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "referer": "https://www.thetimes.com/",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"129\", \"Not=A?Brand\";v=\"8\", \"Chromium\";v=\"129\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "script",
        "sec-fetch-mode": "no-cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0"
    }
    callback = utils.get_url_html(url, headers=headers)
    if not callback:
        return ''
    i = callback.find('{')
    j = callback.rfind('}') + 1
    game_json = json.loads(callback[i:j])
    utils.write_file(game_json, './debug/game.json')

    match_detail = game_json['RRML']['@attributes']
    summary = '<table style="width:90%; margin:auto; padding:8px; text-align:center; border:1px solid #444; border-radius:10px;"><colgroup><col width="15%"><col width="20%"><col width="30%"><col width="20%"><col width="15%"></colgroup>'
    summary += '<tr><td colspan="5"><b>Match Summary</b><br/>{}, {}<br/>{}</td></tr>'.format(utils.format_display_date(datetime.fromisoformat(match_detail['datetime']), False), match_detail['venue'], match_detail['comp_name'])
    summary += '<tr><td><img src="https://omo.akamai.opta.net/image.php?secure=true&h=omo.akamai.opta.net&sport=rugby&entity=team&description=badges&dimensions=65&id={}" /></td>'.format(match_detail['home_team_id'])
    summary += '<td style="font-size:1.05em; font-weight:bold;">{}</td>'.format(match_detail['home_team'])
    summary += '<td style="font-size:1.5em; font-weight:bold;">{}&nbsp;&ndash;&nbsp;{}</td>'.format(match_detail['home_score'], match_detail['away_score'])
    summary += '<td style="font-size:1.05em; font-weight:bold;">{}</td>'.format(match_detail['away_team'])
    summary += '<td><img src="https://omo.akamai.opta.net/image.php?secure=true&h=omo.akamai.opta.net&sport=rugby&entity=team&description=badges&dimensions=65&id={}" /></td></tr>'.format(match_detail['away_team_id'])
    # TODO: past half-time
    summary += '<tr><td colspan="5">HT {}-{}</td></tr>'.format(match_detail['home_ht_score'], match_detail['away_ht_score'])

    if add_stats:
        summary += '<tr><td colspan="5"><br/><b>Match Stats</b></td></tr>'
        stats = {
            "tries": "Tries",
            "passes": "Passes",
            "tackles": "Tackles",
            "runs": "Carries",
            "carries_metres": "Metres gained",
            "lineout_success": "Lineouts won (%)",
            "scrums_success": "Scrums won (%)",
            "turnovers_conceded": "Turnovers conceded",
            "yellow_cards": "Yellow cards",
            "red_cards": "Red cards"
        }
        for team in game_json['RRML']['TeamDetail']['Team']:
            if team['@attributes']['home_or_away'] == 'home':
                home_team = team
            elif team['@attributes']['home_or_away'] == 'away':
                away_team = team
        for key, val in stats.items():
            if key == 'lineout_success':
                # lineout_success = lineouts_won / (lineouts_won + lineouts_Lost)
                won = next((it for it in home_team['TeamStats']['TeamStat'] if 'lineouts_won' in it['@attributes']), None)
                lost = next((it for it in home_team['TeamStats']['TeamStat'] if 'lineouts_Lost' in it['@attributes']), None)
                home_stat_value = round(100 * int(won['@attributes']['lineouts_won']) / (int(won['@attributes']['lineouts_won']) + int(lost['@attributes']['lineouts_Lost'])), 1)
                won = next((it for it in away_team['TeamStats']['TeamStat'] if 'lineouts_won' in it['@attributes']), None)
                lost = next((it for it in away_team['TeamStats']['TeamStat'] if 'lineouts_Lost' in it['@attributes']), None)
                away_stat_value = round(100 * int(won['@attributes']['lineouts_won']) / (int(won['@attributes']['lineouts_won']) + int(lost['@attributes']['lineouts_Lost'])), 1)
            elif key == 'scrums_success':
                # scrums_success = scrums_won / scrums_total
                won = next((it for it in home_team['TeamStats']['TeamStat'] if 'scrums_won' in it['@attributes']), None)
                total = next((it for it in home_team['TeamStats']['TeamStat'] if 'scrums_total' in it['@attributes']), None)
                home_stat_value = round(100 * int(won['@attributes']['scrums_won']) / int(total['@attributes']['scrums_total']), 1)
                won = next((it for it in away_team['TeamStats']['TeamStat'] if 'scrums_won' in it['@attributes']), None)
                total = next((it for it in away_team['TeamStats']['TeamStat'] if 'scrums_total' in it['@attributes']), None)
                away_stat_value = round(100 * int(won['@attributes']['scrums_won']) / int(total['@attributes']['scrums_total']), 1)
            else:
                stat = next((it for it in home_team['TeamStats']['TeamStat'] if key in it['@attributes']), None)
                home_stat_value = stat['@attributes'][key]
                stat = next((it for it in away_team['TeamStats']['TeamStat'] if key in it['@attributes']), None)
                away_stat_value = stat['@attributes'][key]
            summary += '<tr><td colspan="2">{}</td><td>{}</td><td colspan="2">{}</td></tr>'.format(home_stat_value, val, away_stat_value)

    summary += '</table>'
    return summary


def add_opta_cricket_scorecard(game_id):
    # user and password are found in https://secure.widget.cloud.opta.net/v3/v3.opta-widgets.js
    # m = re.search(r'this\.omo_username="([^"]+)"', widget_html)
    # m = re.search(r'this\.omo_password="([^"]+)"', widget_html)
    user = 'OW2017'
    psw = 'dXWg5gVZ'
    url = 'https://omo.akamai.opta.net/auth/?feed_type=c2&game_id={0}&user={1}&psw={2}&jsoncallback=c2_{0}'.format(game_id, user, psw)
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "referer": "https://www.thetimes.com/",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"129\", \"Not=A?Brand\";v=\"8\", \"Chromium\";v=\"129\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "script",
        "sec-fetch-mode": "no-cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0"
    }
    callback = utils.get_url_html(url, headers=headers)
    if not callback:
        return ''
    i = callback.find('{')
    j = callback.rfind('}') + 1
    game_json = json.loads(callback[i:j])
    utils.write_file(game_json, './debug/game.json')
    match_detail = game_json['CricketMatchSummary']['MatchDetail']['@attributes']
    venue = game_json['CricketMatchSummary']['MatchDetail']['Venue']['@attributes']
    scorecard = '<table style="width:90%; margin:auto; padding:8px; text-align:center; border:1px solid #444; border-radius:10px;">'
    scorecard += '<tr><td><img src="https://omo.akamai.opta.net/image.php?secure=true&h=omo.akamai.opta.net&sport=cricket&entity=team&description=badges&dimensions=65&id={}" /></td>'.format(match_detail['home_team_id'])
    scorecard += '<td><h4>{} v {}</h4><div>{}</div><div>{} - {}</div><div>Venue: {}, {}, {}</div><h4>{}<br/>{}</h4></td>'.format(match_detail['home_team'], match_detail['away_team'], match_detail['competition_name'], match_detail['description'], match_detail['game_date'], venue['venue_name'], venue['venue_city'], venue['venue_country'], match_detail['result'], match_detail['series_status'])
    scorecard += '<td><img src="https://omo.akamai.opta.net/image.php?secure=true&h=omo.akamai.opta.net&sport=cricket&entity=team&description=badges&dimensions=65&id={}" /></td></tr>'.format(match_detail['away_team_id'])
    scorecard += '</table>'
    return scorecard


def get_feed(url, args, site_json, save_debug=False):
    times_state = get_window_state(url, 'TIMES_STATE')
    if not times_state:
        return None
    if save_debug:
        utils.write_file(times_state, './debug/feed.json')

    netloc = urlsplit(url).netloc
    n = 0
    feed_items = []
    for section in times_state['preloadedData']['tpaData']['page']['body']:
        if section['__typename'] == 'Collection':
            for child in section['children']:
                if child['__typename'] == 'PageSlice':
                    for c in child['children']:
                        if c['__typename'] == 'ArticleReference':
                            article_url = 'https://' + netloc + c['article']['url']
                            if save_debug:
                                logger.debug('getting content for ' + article_url)
                            item = get_content(article_url, args, site_json, save_debug)
                            if item:
                                if utils.filter_item(item, args) == True:
                                    feed_items.append(item)
                        else:
                            logger.warning('unhandled PageSlice child type {} in {}'.format(c['__typename'], url))
                else:
                    logger.warning('unhandled Collection child type {} in {}'.format(child['__typename'], url))
        else:
            logger.warning('unhandled section type {} in {}'.format(section['__typename'], url))

    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
