import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

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

    if 'archive' in paths:
        query = '?page=' + paths[-1]
    else:
        query = ''

    next_url = 'https://static-web-prod.actionnetwork.com/_next/data/{}{}{}'.format(site_json['buildId'], path, query)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url, site_json=site_json)
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


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/next.json')
    article_json = next_data['pageProps']['article']
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')
    return get_item(article_json, args, site_json, save_debug)


def get_item(article_json, args, site_json, save_debug):
    item = {}
    item['id'] = article_json['id']

    if article_json.get('canonical_url'):
        item['url'] = article_json['canonical_url']
    elif article_json.get('url'):
        item['url'] = article_json['url']
    elif article_json['type'] == 'audio':
        if article_json['channel']['name'] == 'BUCKETS':
            item['url'] = 'https://shows.acast.com/buckets/episodes/' + article_json['source_id']

    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['published_at'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('updated_at'):
        dt = datetime.fromisoformat(article_json['updated_at'])
        item['date_modified'] = dt.isoformat()


    item['authors'] = []
    if article_json.get('channel'):
        item['authors'].append({"name": article_json['channel']['name']})
    if article_json.get('authors'):
        if article_json['authors'][0].get('name'):
            item['authors'] = [{"name": x['name']} for x in article_json['authors']]
        elif article_json['authors'][0].get('display_name'):
            item['authors'] = [{"name": x['display_name']} for x in article_json['authors']]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = []
    if article_json.get('category'):
        item['tags'].append(article_json['category']['name'])
    elif article_json.get('categories'):
        item['tags'] += [x['name'] for x in article_json['categories']]
    if article_json.get('tags'):
        item['tags'] += [x['name'] for x in article_json['tags']]

    if article_json.get('excerpt'):
        item['summary'] = article_json['excerpt']
    elif article_json.get('meta_description'):
        item['summary'] = article_json['meta_description']
    elif article_json.get('description'):
        item['summary'] = article_json['description']

    item['content_html'] = ''
    if article_json.get('feature_image'):
        item['image'] = article_json['feature_image']
        if article_json.get('feature_image_caption'):
            caption = re.sub(r'^<p>|</p>$', '', article_json['feature_image_caption'])
        else:
            caption = ''
        item['content_html'] += utils.add_image(item['image'], caption)
    elif article_json.get('image_urls'):
        item['image'] = article_json['image_urls'][0]

    if article_json['type'] == 'video' or article_json['type'] == 'audio':
        item['content_html'] = utils.add_embed(item['url'])
        if 'embed' not in args and 'summary' in item:
            item['content_html'] += '<p>' + item['summary'] + '</p>'
            return item

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if save_debug:
        utils.write_file(article_json['html'], './debug/debug.html')

    game_json = None
    def add_playercomparison(matchobj):
        params = {}
        for m in re.findall(r'([^=\s]+)="([^"\u201d]+)', matchobj.group(1)):
            params[m[0]] = m[1]
        if not params.get('homeplayerid') or not params.get('awayplayerid'):
            logger.warning('unhandled playercomparison ' + matchobj.group(0))
            return matchobj.group(0)

        home_player = utils.get_url_json('https://api.actionnetwork.com/web/v2/players/{}/details/stats'.format(params['homeplayerid']))
        away_player = utils.get_url_json('https://api.actionnetwork.com/web/v2/players/{}/details/stats'.format(params['awayplayerid']))
        if not home_player or not away_player:
            return matchobj.group(0)

        if home_player['current_season'] != away_player['current_season']:
            logger.warning('playercomparison current_season mismatch')
            return matchobj.group(0)

        playercomparison = ''
        if params.get('title'):
            playercomparison += '<h3 style="text-align:center;">' + params['title'] + '</h3>'
        playercomparison += '<table style="width:100%; border-collapse:collapse;"><tr style="background-color:#aaa;"><th style="text-align:center; padding:8px;">' + params['awayplayerdisplay'] + '</th><th style="text-align:center; padding:8px;">Stat</th><th style="text-align:center; padding:8px;">' + params['homeplayerdisplay'] + '</th></tr>'

        season = str(home_player['current_season'])
        if params.get('stattype'):
            stattype = params['stattype']
        else:
            stattype = 'average'
        
        if stattype in home_player['stats'][season]['reg']:
            home_stats = home_player['stats'][season]['reg'][stattype]
            away_stats = home_player['stats'][season]['reg'][stattype]
        elif stattype in home_player['stats'][season]['reg']['total']:
            home_stats = home_player['stats'][season]['reg']['total'][stattype]
            away_stats = home_player['stats'][season]['reg']['total'][stattype]
        if 'stats' in home_stats:
            home_stats = home_stats['stats']            
            away_stats = away_stats['stats']

        for i, (key, home_val) in enumerate(home_stats.items()):
            playercomparison += '<tr style="border-top:1px solid light-dark(#333,#ccc);'
            if i % 2:
                playercomparison += ' background-color:light-dark(#ccc,#333);'
            playercomparison += '">'
            if isinstance(val, dict):
                playercomparison += '<td></td><td style="text-align:center; padding:8px;">' + key.replace('_', ' ').title() + '</td><td></td>'
            else:
                away_val = away_stats[key]
                if re.search(r'\.\d{2,}', str(away_val)):
                    val = '{:.2f}'.format(away_val)
                else:
                    val = str(away_val)
                playercomparison += '<td style="text-align:center; padding:8px;">' + val + '</td>'
                playercomparison += '<td style="text-align:center; padding:8px;">' + key.replace('_', ' ').title() + '</td>'
                if re.search(r'\.\d{2,}', str(home_val)):
                    val = '{:.2f}'.format(home_val)
                else:
                    val = str(home_val)
                playercomparison += '<td style="text-align:center; padding:8px;">' + val + '</td>'
            playercomparison += '</tr>'
        playercomparison += '</table>'
        return playercomparison

    def add_gameinjuries(matchobj):
        nonlocal game_json
        params = {}
        for m in re.findall(r'([^=\s]+)="([^"\u201d]+)', matchobj.group(1)):
            params[m[0]] = m[1]
        gameinjuries = ''
        if params.get('gameid'):
            if not game_json or game_json['id'] != int(params['gameid']):
                game_json = utils.get_url_json('https://api.actionnetwork.com/web/v2/games/{}/static'.format(params['gameid']))
            if game_json:
                injuries = utils.get_url_json('https://api.actionnetwork.com/web/v1/leagues/{}/injuries'.format(game_json['league_id']))
                if injuries:
                    n = len(game_json['teams'])
                    for i in range(n):
                        game_json['teams'][i]['injuries'] = []
                    for injury in injuries['injuries']:
                        for i in range(n):
                            if injury['team']['display_name'] == game_json['teams'][i]['display_name']:
                                game_json['teams'][0]['injuries'].append(injury)
                    gameinjuries += '<h3 style="text-align:center;">' + game_json['teams'][0]['full_name'] + ' vs. ' + game_json['teams'][1]['full_name'] + ' Injury Report</h3>'
                    for i in range(n):
                        gameinjuries += '<div style="font-weight:bold;">' + game_json['teams'][i]['display_name'] + ' Injuries</div><ul>'
                        if len(game_json['teams'][i]['injuries']) == 0:
                            gameinjuries += '<li>No injuries reported</li>'
                        else:
                            for injury in game_json['teams'][i]['injuries']:
                                gameinjuries += '<li>' + injury['player']['position'] + ' ' + injury['player']['full_name'] + ' is ' + injury['status'] + ' with ' + injury['description'].lower() + '</li>'
                        gameinjuries += '</ul>'
        return gameinjuries

    def add_bettingtrends(matchobj):
        nonlocal game_json
        params = {}
        for m in re.findall(r'([^=\s]+)="([^"\u201d]+)', matchobj.group(1)):
            params[m[0]] = m[1]
        bettingtrends = ''
        if params.get('gameid'):
            if not game_json or game_json['id'] != int(params['gameid']):
                game_json = utils.get_url_json('https://api.actionnetwork.com/web/v2/games/{}/static'.format(params['gameid']))
            if game_json:
                bettingtrends += '<ul>'
                spread = game_json['markets']['15']['event']['spread']
                if spread[0]['bet_info']['tickets']['percent'] >= spread[1]['bet_info']['tickets']['percent']:
                    tickets = spread[0]
                else:
                    tickets = spread[1]
                if spread[0]['bet_info']['money']['percent'] >= spread[1]['bet_info']['money']['percent']:
                    money = spread[0]
                else:
                    money = spread[1]
                if tickets['team_id'] == money['team_id']:
                    team = next((it for it in game_json['teams'] if it['id'] == tickets['team_id']), None)
                    bettingtrends += '<li>{:.0f}% of bets and {:.0f}% of the money are on the {} to cover the <a href="https://www.actionnetwork.com/education/point-spread">spread</a></li>'.format(tickets['bet_info']['tickets']['percent'], money['bet_info']['money']['percent'], team['display_name'])
                else:
                    team = next((it for it in game_json['teams'] if it['id'] == tickets['team_id']), None)
                    bettingtrends += '<li>{:.0f}% of bets are on the {} to cover the <a href="https://www.actionnetwork.com/education/point-spread">spread</a>, and '.format(tickets['bet_info']['tickets']['percent'], team['display_name'])
                    team = next((it for it in game_json['teams'] if it['id'] == money['team_id']), None)
                    bettingtrends += '{:.0f}% of the money are on the {} to cover the <a href="https://www.actionnetwork.com/education/point-spread">spread</a></li>'.format(money['bet_info']['money']['percent'], team['display_name'])
                moneyline = game_json['markets']['15']['event']['moneyline']
                if moneyline[0]['bet_info']['tickets']['percent'] >= moneyline[1]['bet_info']['tickets']['percent']:
                    tickets = moneyline[0]
                else:
                    tickets = moneyline[1]
                if moneyline[0]['bet_info']['money']['percent'] >= moneyline[1]['bet_info']['money']['percent']:
                    money = moneyline[0]
                else:
                    money = moneyline[1]
                if tickets['team_id'] == money['team_id']:
                    team = next((it for it in game_json['teams'] if it['id'] == tickets['team_id']), None)
                    bettingtrends += '<li>{:.0f}% of bets and {:.0f}% of the money on the <a href="https://www.actionnetwork.com/education/moneyline">moneyline</a> are on the {} to win outright</li>'.format(tickets['bet_info']['tickets']['percent'], money['bet_info']['money']['percent'], team['display_name'])
                else:
                    team = next((it for it in game_json['teams'] if it['id'] == tickets['team_id']), None)
                    bettingtrends += '<li>{:.0f}% of bets on the <a href="https://www.actionnetwork.com/education/moneyline">moneyline</a> are on the {} to win outright, and '.format(tickets['bet_info']['tickets']['percent'], team['display_name'])
                    team = next((it for it in game_json['teams'] if it['id'] == money['team_id']), None)
                    bettingtrends += '{:.0f}% of money on the <a href="https://www.actionnetwork.com/education/moneyline">moneyline</a> are on the {} to win outright'.format(money['bet_info']['money']['percent'], team['display_name'])
                total = game_json['markets']['15']['event']['total']
                if total[0]['bet_info']['tickets']['percent'] >= total[1]['bet_info']['tickets']['percent']:
                    tickets = total[0]
                else:
                    tickets = total[1]
                if total[0]['bet_info']['money']['percent'] >= total[1]['bet_info']['money']['percent']:
                    money = total[0]
                else:
                    money = total[1]
                if tickets['side'] == money['side']:
                    bettingtrends += '<li>{:.0f}% of bets and {:.0f}% of the money are on the {}</li>'.format(tickets['bet_info']['tickets']['percent'], money['bet_info']['money']['percent'], tickets['side'])
                else:
                    bettingtrends += '<li>{:.0f}% of bets are on the {}, and '.format(tickets['bet_info']['tickets']['percent'], tickets['side'])
                    bettingtrends += '{:.0f}% of the money are on the {}</li>'.format(money['bet_info']['money']['percent'], money['side'])
                bettingtrends += '</ul>'
                bettingtrends += '<p><em>Betting trends via our live, updating <a href="https://www.actionnetwork.com/{}/public-betting">{} public betting & money percentages</a> page.</em></p>'.format(game_json['league_name'], game_json['league_name'].upper())
        return bettingtrends

    def add_gameforecast(matchobj):
        nonlocal game_json
        params = {}
        for m in re.findall(r'([^=\s]+)="([^"\u201d]+)', matchobj.group(1)):
            params[m[0]] = m[1]
        gameforecast = ''
        if params.get('gameid'):
            if not game_json or game_json['id'] != int(params['gameid']):
                game_json = utils.get_url_json('https://api.actionnetwork.com/web/v2/games/{}/static'.format(params['gameid']))
            if game_json:
                gameforecast = '<div style="display:grid; grid-template-areas:\'header header header\' \'teams forecast forecast\' \'teams precip wind\'; grid-template-columns:2fr 3fr 3fr; align-content:center; padding:8px; border:1px solid light-dark(#333,#ccc); border-radius:10px;">'
                gameforecast += '<div style="grid-area:header;"><strong>Game Forecast</strong><br/><small>From <a href="https://www.actionnetwork.com/{}/weather">{} Weather</a></div>'.format(game_json['league_name'], game_json['league_name'].upper())
                gameforecast += '<div style="grid-area:teams; text-align:center; border:1px solid light-dark(#333,#ccc); border-radius:10px; margin:8px; padding:8px;">'
                gameforecast += '<img src="' + game_json['teams'][0]['logo'] + '" style="width:24px; height:24px;">'
                gameforecast += '<img src="' + game_json['teams'][1]['logo'] + '" style="width:24px; height:24px;">'
                gameforecast += '<br/><strong>' + game_json['teams'][0]['abbr'] + ' @ ' + game_json['teams'][1]['abbr'] + '</strong>'
                gameforecast += '<br/><small>' + utils.format_display_date(datetime.fromisoformat(game_json['start_time'])) + '</small></div>'
                gameforecast += '<div style="grid-area:forecast; border:1px solid light-dark(#333,#ccc); border-radius:10px; margin:8px; padding:0 8px;">'
                gameforecast += '<img src="' + game_json['weather']['icon'] + '" style="float:right; width:48px; height:48px;">'
                gameforecast += '<small>Forecast</small><br/><strong>{:.0f}°F {}</strong></div>'.format(game_json['weather']['temperature'], game_json['weather']['description'])
                gameforecast += '<div style="grid-area:precip; border:1px solid light-dark(#333,#ccc); border-radius:10px; margin:8px; padding:0 8px;"><small>Precipitation</small><br/><strong>{:.0f}%</strong></div>'.format(game_json['weather']['precipitation'])
                gameforecast += '<div style="grid-area:wind; border:1px solid light-dark(#333,#ccc); border-radius:10px; margin:8px; padding:0 8px;"><small>Wind</small><br/><strong>{:.2f} '.format(game_json['weather']['wind_speed'])
                if game_json['weather']['wind_degrees'] <= 11:
                    gameforecast += 'N'
                elif game_json['weather']['wind_degrees'] <= 33:
                    gameforecast += 'NNE'
                elif game_json['weather']['wind_degrees'] <= 56:
                    gameforecast += 'NE'
                elif game_json['weather']['wind_degrees'] <= 79:
                    gameforecast += 'ENE'
                elif game_json['weather']['wind_degrees'] <= 102:
                    gameforecast += 'E'
                elif game_json['weather']['wind_degrees'] <= 125:
                    gameforecast += 'ESE'
                elif game_json['weather']['wind_degrees'] <= 147:
                    gameforecast += 'SE'
                elif game_json['weather']['wind_degrees'] <= 170:
                    gameforecast += 'SSE'
                elif game_json['weather']['wind_degrees'] <= 191:
                    gameforecast += 'S'
                elif game_json['weather']['wind_degrees'] <= 214:
                    gameforecast += 'SSW'
                elif game_json['weather']['wind_degrees'] <= 237:
                    gameforecast += 'SW'
                elif game_json['weather']['wind_degrees'] <= 260:
                    gameforecast += 'WSW'
                elif game_json['weather']['wind_degrees'] <= 283:
                    gameforecast += 'W'
                elif game_json['weather']['wind_degrees'] <= 306:
                    gameforecast += 'WNW'
                elif game_json['weather']['wind_degrees'] <= 329:
                    gameforecast += 'NW'
                elif game_json['weather']['wind_degrees'] <= 352:
                    gameforecast += 'NNW'
                elif game_json['weather']['wind_degrees'] <= 360:
                    gameforecast += 'N'
                gameforecast += '</strong></div>'
                gameforecast += '</div>'
        return gameforecast

    def add_howtowatch(matchobj):
        nonlocal game_json
        params = {}
        for m in re.findall(r'([^=\s]+)="([^"\u201d]+)', matchobj.group(1)):
            params[m[0]] = m[1]
        howtowatch = ''
        if params.get('gameid'):
            if not game_json or game_json['id'] != int(params['gameid']):
                game_json = utils.get_url_json('https://api.actionnetwork.com/web/v2/games/{}/static'.format(params['gameid']))
            if game_json:
                howtowatch += '<h3 style="text-align:center;">How To Watch ' + game_json['teams'][0]['display_name'] + ' vs. ' + game_json['teams'][1]['display_name'] + '</h3><table>'
                howtowatch += '<tr><td><b>Location:</b></td><td>' + game_json['venue']['name'] + ' in ' + game_json['venue']['city'] + ', ' + game_json['venue']['state'] + '</td></tr>'
                howtowatch += '<tr><td><b>Date:</b></td><td>' + utils.format_display_date(datetime.fromisoformat(game_json['start_time']), date_only=True) + '</td></tr>'
                howtowatch += '<tr><td><b>Time:</b></td><td>' + utils.format_display_date(datetime.fromisoformat(game_json['start_time']), time_only=True) + '</td></tr>'
                if game_json['broadcast'].get('network'):
                    howtowatch += '<tr><td><b>TV:</b></td><td>' + game_json['broadcast']['network'] + '</td></tr>'
                if game_json['broadcast'].get('internet'):
                    howtowatch += '<tr><td><b>Streaming:</b></td><td>' + game_json['broadcast']['internet'] + '</td></tr>'
                howtowatch += '</table>'
        return howtowatch

    def add_subheader(matchobj):
        params = {}
        for m in re.findall(r'([^=\s]+)="([^"\u201d]+)', matchobj.group(1)):
            params[m[0]] = m[1]
        subheader = '<div style="display:flex;'
        if params.get('center') == 'true':
            subheader += ' justify-content:center;'
        subheader += '">'
        if params.get('link1'):
            subheader += '<a href="' + params['link1'] + '" target="_blank">'
        if params.get('logo1url'):
            subheader += '<img src="' + params['logo1url'] + '" style="margin:auto 0; width:32px; height:32px;">'
        if params.get('link1'):
            subheader += '</a>'
        if params.get('link2'):
            subheader += '<a href="' + params['link2'] + '" target="_blank">'
        if params.get('logo2url'):
            subheader += '<img src="' + params['logo2url'] + '" style="margin:auto 0; width:32px; height:32px;">'
        if params.get('link2'):
            subheader += '</a>'
        if params.get('text'):
            subheader += '<span style="margin:auto 4px; font-weight:bold;'
            if params.get('sizedown') == 'false':
                subheader += ' font-size:1.1em;'
            subheader += '">' + params['text'] + '</div>'
        subheader += '</div>'
        return subheader

    def add_quickslipbasic(matchobj):
        params = {}
        for m in re.findall(r'([^=\s]+)="([^"\u201d]+)', matchobj.group(1)):
            params[m[0]] = m[1]
        quickslip = '<div style="width:360px; margin:auto; padding:8px; border:1px solid light-dark(#333,#ccc); border-radius:10px;">'
        if params.get('booklogo'):
            quickslip += '<img src="' + params['booklogo'] + '" style="width:100%;">'
        if params.get('image'):
            quickslip += '<img src="' + params['image'] + '" style="width:100%;">'
        if params.get('buttonlink'):
            quickslip += utils.add_button(params['buttonlink'], params['buttontext'])
        quickslip += '</div>'
        return quickslip

    def add_gameheader(matchobj):
        params = {}
        for m in re.findall(r'([^=\s]+)="([^"\u201d]+)', matchobj.group(1)):
            params[m[0]] = m[1]
        gameheader = '<div style="display:grid; grid-template-areas:\'awaylogo datetime homelogo\' \'pick pick pick\'; align-content:center; padding:8px; border:1px solid light-dark(#333,#ccc); border-radius:10px;">'
        link = 'https://www.actionnetwork.com/{}/odds/{}'.format(params['league'], params['awayslug'])
        gameheader += '<div style="grid-area:awaylogo; text-align:center;"><a href="' + link + '"><img src="' + params['awaylogo'] + '" style="width:72px; height:72px;"></a></div>'
        gameheader += '<div style="grid-area:datetime; font-weight:bold; text-align:center;">'
        if params.get('date'):
            gameheader += params['date'] + '<br>'
        if params.get('time'):
            gameheader += params['time'] + '<br>'
        if params.get('network'):
            gameheader += params['network'] + '<br>'
        gameheader = gameheader[:-4] + '</div>'
        link = 'https://www.actionnetwork.com/{}/odds/{}'.format(params['league'], params['homeslug'])
        gameheader += '<div style="grid-area:homelogo; text-align:center;"><a href="' + link + '"><img src="' + params['homelogo'] + '" style="width:72px; height:72px;"></a></div>'
        gameheader += '<div style="grid-area:pick; border-top:1px solid light-dark(#333,#ccc);"><div style="display:flex; justify-content:center; align-items:center; margin:8px 0 0 0;">'
        if params.get('haspick') == 'true':
            gameheader += '<strong>' + params['picktext'] + '</strong>'
        if params.get('bookprimarylogo'):
            gameheader += '<img src="' + params['bookprimarylogo'] + '" style="height:2em; padding-left:8px;">'
        gameheader += '</div></div></div>'
        return gameheader

    def add_gamematchup(matchobj):
        params = {}
        for m in re.findall(r'([^=\s]+)="([^"\u201d]+)', matchobj.group(1)):
            params[m[0]] = m[1]
        gamematchup = '<div style="display:grid; grid-template-areas:\'awaylogo awaylogo datetime datetime homelogo homelogo\' \'awayname awayname awayname homename homename homename\' \'col1awaytext col2awaytext col3awaytext col1hometext col2hometext col3hometext\' \'col1awayval col2awayval col3awayval col1homeval col2homeval col3homeval\'; align-content:center; padding:8px; border:1px solid light-dark(#333,#ccc); border-radius:10px;">'
        link = 'https://www.actionnetwork.com/{}/odds/{}'.format(params['league'], params['awayslug'])
        gamematchup += '<div style="grid-area:awaylogo; text-align:center;"><a href="' + link + '"><img src="' + params['awaylogo'] + '" style="width:72px; height:72px;"></a></div>'
        gamematchup += '<div style="grid-area:datetime; font-weight:bold; text-align:center;">'
        if params.get('date'):
            gamematchup += params['date'] + '<br>'
        if params.get('time'):
            gamematchup += params['time'] + '<br>'
        if params.get('network'):
            gamematchup += params['network'] + '<br>'
        gamematchup = gamematchup[:-4] + '</div>'
        link = 'https://www.actionnetwork.com/{}/odds/{}'.format(params['league'], params['homeslug'])
        gamematchup += '<div style="grid-area:homelogo; text-align:center;"><a href="' + link + '"><img src="' + params['homelogo'] + '" style="width:72px; height:72px;"></a></div>'
        gamematchup += '<div style="grid-area:awayname; font-size:1.1em; font-weight:bold; text-align:center; padding:8px; border-right:1px solid light-dark(#333,#ccc);">' + params['awayname'] + ' Odds</div>'
        gamematchup += '<div style="grid-area:homename; font-size:1.1em; font-weight:bold; text-align:center; padding:8px;">' + params['homename'] + ' Odds</div>'
        gamematchup += '<div style="grid-area:col1awaytext; font-weight:bold; text-align:center; padding:8px; border-right:1px solid light-dark(#333,#ccc);">' + params['col1text'] + '</div>'
        gamematchup += '<div style="grid-area:col1awayval; text-align:center; border-right:1px solid light-dark(#333,#ccc);"><b>' + params['col1awaytext'] + '</b>'
        if params.get('col1awayline'):
            gamematchup += '<br><span style="color:gray; font-size:0.8em;">' + params['col1awayline'] + '</span>'
        gamematchup += '</div>'
        gamematchup += '<div style="grid-area:col2awaytext; font-weight:bold; text-align:center; padding:8px; border-right:1px solid light-dark(#333,#ccc);">' + params['col2text'] + '</div>'
        gamematchup += '<div style="grid-area:col2awayval; text-align:center; border-right:1px solid light-dark(#333,#ccc);"><b>' + params['col2awaytext'] + '</b>'
        if params.get('col2awayline'):
            gamematchup += '<br><span style="color:gray; font-size:0.8em;">' + params['col2awayline'] + '</span>'
        gamematchup += '</div>'
        gamematchup += '<div style="grid-area:col3awaytext; font-weight:bold; text-align:center; padding:8px; border-right:1px solid light-dark(#333,#ccc);">' + params['col3text'] + '</div>'
        gamematchup += '<div style="grid-area:col3awayval; text-align:center; border-right:1px solid light-dark(#333,#ccc);"><b>' + params['col3awaytext'] + '</b>'
        if params.get('col3awayline'):
            gamematchup += '<br><span style="color:gray; font-size:0.8em;">' + params['col3awayline'] + '</span>'
        gamematchup += '</div>'

        gamematchup += '<div style="grid-area:col1hometext; font-weight:bold; text-align:center; padding:8px; border-right:1px solid light-dark(#333,#ccc);">' + params['col1text'] + '</div>'
        gamematchup += '<div style="grid-area:col1homeval; text-align:center; border-right:1px solid light-dark(#333,#ccc);"><b>' + params['col1hometext'] + '</b>'
        if params.get('col1homeline'):
            gamematchup += '<br><span style="color:gray; font-size:0.8em;">' + params['col1homeline'] + '</span>'
        gamematchup += '</div>'
        gamematchup += '<div style="grid-area:col2hometext; font-weight:bold; text-align:center; padding:8px; border-right:1px solid light-dark(#333,#ccc);">' + params['col2text'] + '</div>'
        gamematchup += '<div style="grid-area:col2homeval; text-align:center; border-right:1px solid light-dark(#333,#ccc);"><b>' + params['col2hometext'] + '</b>'
        if params.get('col2homeline'):
            gamematchup += '<br><span style="color:gray; font-size:0.8em;">' + params['col2homeline'] + '</span>'
        gamematchup += '</div>'
        gamematchup += '<div style="grid-area:col3hometext; font-weight:bold; text-align:center; padding:8px;">' + params['col3text'] + '</div>'
        gamematchup += '<div style="grid-area:col3homeval; text-align:center;"><b>' + params['col3hometext'] + '</b>'
        if params.get('col3homeline'):
            gamematchup += '<br><span style="color:gray; font-size:0.8em;">' + params['col3homeline'] + '</span>'
        gamematchup += '</div>'
        gamematchup += '</div>'
        return gamematchup

    def add_teammatchup(matchobj):
        params = {}
        for m in re.findall(r'([^=\s]+)="([^"\u201d]+)', matchobj.group(1)):
            params[m[0]] = m[1]
        teammatchup = '<div style="width:100%; text-align:center;">'
        if params.get('text'):
            teammatchup += '<div style="display:flex; justify-content:center;">'
        if params.get('link'):
            teammatchup += '<a href="' + params['link'] + '">'
        if params.get('firstlogo'):
            teammatchup += '<img src="{}" alt="{}" style="margin:auto 0; width:32px; height:32px;">'.format(params['firstlogo'], params['firstfullname'])
        if params.get('secondlogo'):
            teammatchup += '<img src="{}" alt="{}" style="margin:auto 0; width:32px; height:32px;">'.format(params['secondlogo'], params['secondfullname'])
        if params.get('link'):
            teammatchup += '</a>'
        if params.get('text'):
            teammatchup += '<span style="margin:auto 4px; font-weight:bold;">' + params['text'] + '</span></div>'
        teammatchup += '</div>'
        return teammatchup

    def add_anchor(matchobj):
        params = {}
        for m in re.findall(r'([^=\s]+)="([^"\u201d]+)', matchobj.group(1)):
            params[m[0]] = m[1]
        return '<a name="' + params['name'] + '"></a>'

    def add_embed(matchobj):
        m = re.search(r'src="([^"]+)', matchobj.group(0))
        if m:
            return utils.add_embed(m.group(1))

    def format_table(matchobj):
        soup = BeautifulSoup(matchobj.group(0), 'html.parser')
        soup.table.attrs = {}
        soup.table['style'] = 'width:100%; border-collapse:collapse; border-style:hidden; border-radius:10px; box-shadow:0 0 0 1px light-dark(#333,#ccc);'
        for tr in soup.find_all('tr'):
            tr.attrs = {}
            tr['style'] = 'border-bottom:1px solid light-dark(#333,#ccc);'
        for td in soup.find_all(['td', 'th']):
            if td.get('class'):
                del td['class']
            td['style'] = 'padding:8px; text-align:center;'
        return str(soup)

    def format_figure(matchobj):
        soup = BeautifulSoup(matchobj.group(0), 'html.parser')
        if not soup.img:
            logger.warning('unhandled figure ' + matchobj.group(0))
            return matchobj.group(0)
        if soup.img.get('srcset'):
            img_src = utils.image_from_srcset(soup.img['srcset'], 1200)
        else:
            img_src = soup.img['src']
        if soup.figcaption:
            caption = soup.figcaption.decode_contents()
        else:
            caption = ''
        return utils.add_image(img_src, caption)

    if article_json.get('odds_banner') and article_json['odds_banner'].get('enabled') == True:
        item['content_html'] += '<div style="margin:0.5em; text-align:center;"><span style="display:inline-block; min-width:180px; padding:0.5em; margin:0.5em; font-size:1.2em; border:1px solid light-dark(#333,#ccc); border-radius:10px;"><small>Expert Pick ({}):</small><br/><strong>{}</strong></span></div>'.format(article_json['odds_banner']['expert_pick']['type'], article_json['odds_banner']['expert_pick']['display'])

    item['content_html'] += article_json['html']
    item['content_html'] = re.sub(r'<table (.*?)</table>', format_table, item['content_html'], flags=re.S)
    item['content_html'] = re.sub(r'<figure (.*?)</figure>', format_figure, item['content_html'], flags=re.S)
    item['content_html'] = re.sub(r'\[subheader (.*?)\]\[/subheader\]', add_subheader, item['content_html'])
    item['content_html'] = re.sub(r'\[quickslipbasic (.*?)\]\[/quickslipbasic\]', add_quickslipbasic, item['content_html'])
    item['content_html'] = re.sub(r'\[gameforecast (.*?)\]\[/gameforecast\]', add_gameforecast, item['content_html'])
    item['content_html'] = re.sub(r'\[gameheader (.*?)\]\[/gameheader\]', add_gameheader, item['content_html'])
    item['content_html'] = re.sub(r'\[gameinjuries (.*?)\]\[/gameinjuries\]', add_gameinjuries, item['content_html'])
    item['content_html'] = re.sub(r'\[gamematchup (.*?)\]\[/gamematchup\]', add_gamematchup, item['content_html'])
    item['content_html'] = re.sub(r'\[teammatchup (.*?)\]\[/teammatchup\]', add_teammatchup, item['content_html'])
    item['content_html'] = re.sub(r'\[playercomparison (.*?)\]\[/playercomparison\]', add_playercomparison, item['content_html'])
    item['content_html'] = re.sub(r'\[bettingtrends (.*?)\]\[/bettingtrends\]', add_bettingtrends, item['content_html'])
    item['content_html'] = re.sub(r'<p>\[howtowatch (.*?)\]\[/howtowatch\]</p>', add_howtowatch, item['content_html'])
    item['content_html'] = re.sub(r'\s*<p><iframe (.*?)</p>\s*', add_embed, item['content_html'])
    item['content_html'] = re.sub(r'\[anchor (.*?)\]\[/anchor\]', add_anchor, item['content_html'])

    item['content_html'] = re.sub(r'\[betlabsembed (.*?)\]\[/betlabsembed\]', '', item['content_html'])
    item['content_html'] = re.sub(r'\[procard (.*?)\]\[/procard\]', '', item['content_html'])
    item['content_html'] = re.sub(r'\[relatedarticle (.*?)\]\[/relatedarticle\]', '', item['content_html'])
    item['content_html'] = re.sub(r'\s*<(div|p)>_InlineAdBlock</(div|p)>\s*', '', item['content_html'])
    item['content_html'] = re.sub(r'<br />\s*_InlineAdBlock', '', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if 'archive' in paths:
        next_data = get_next_data(url, site_json)
        if not next_data:
            return None
        if save_debug:
            utils.write_file(next_data, './debug/feed.json')

        n = 0
        feed_items = []
        for article in next_data['pageProps']['articles']:
            if article['type'] == 'article':
                if save_debug:
                    logger.debug('getting content for ' + article['url'])
                item = get_content(article['url'], args, site_json, save_debug)
            elif article['type'] == 'video':
                if save_debug:
                    logger.debug('getting content for ' + article['url'])
                item = get_item(article, args, site_json, save_debug)
            elif article['type'] == 'audio':
                # if save_debug:
                #     logger.debug('getting content for ' + article['url'])
                item = get_item(article, args, site_json, save_debug)
            else:
                logger.warning('unhandled article type {} in {}'.format(article['type'], url))
                continue
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break

        feed = utils.init_jsonfeed(args)
        if next_data['pageProps'].get('category'):
            feed['title'] = next_data['pageProps']['category'].upper() + ' | Action Network'
        feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
        return feed