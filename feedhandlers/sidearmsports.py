import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def add_video(video_id, netloc):
    api_url = 'https://{}/services/allaccess.ashx/2/media/get?type=Archive&id={}'.format(netloc, video_id)
    api_json = utils.get_url_json(api_url)
    content_html = ''
    if api_json:
        utils.write_file(api_json, './debug/video.json')
        video = api_json['data'][0]
        content_html = utils.add_video(video['formats']['MobileH264'], 'application/x-mpegURL', video['poster'], video['title'])
    return content_html


def add_game_stats(game, sport, netloc, team):
    allowed_sports = ["baseball", "basketball", "field-hockey", "football", "hockey", "lacrosse", "softball", "soccer", "volleyball", "wpolo"]
    api_json = None
    if sport in allowed_sports and game.get('postStoryId'):
        api_url = 'https://{}/api/v2/Stats/{}/game-teams?storyId={}'.format(netloc, sport, game['postStoryId'])
        # print(api_url)
        api_json = utils.get_url_json(api_url)

    if api_json and isinstance(api_json, list):
        utils.write_file(api_json, './debug/game.json')
        game_stats = api_json[0]
        if game_stats['home'].get('lineScore'):
            a = 'lineScore'
        elif game_stats['home'].get('scoreSummary'):
            a = 'scoreSummary'
        if game_stats['home'][a].get('periodSummaries'):
            b = 'periodSummaries'
            c = 'period'
            d = 'score'
        elif game_stats['home'][a].get('gameSummaries'):
            b = 'gameSummaries'
            c = 'game'
            d = 'points'

        content_html = '<table style="margin-left:auto; margin-right:auto;"><tr style="text-align:center; padding:8px;">'
        content_html += '<td style="text-align:center; padding:8px;"><b>{}</b><br/><small>{}</small></td>'.format(game_stats['visit']['name'], game_stats['visit']['record'])
        if game_stats['visitTeam'].get('imageUrl'):
            logo = 'https://{}{}'.format(netloc, game_stats['visitTeam']['imageUrl'])
        else:
            logo = '{}/image?width=64&height=64'.format(config.server)
        content_html += '<td><img src="{}" style="width:64px;" /></td>'.format(logo)
        content_html += '<td style="text-align:center; padding:8px;"><span style="font-size:2em; font-weight:bold;">{}</span> vs. <span style="font-size:2em; font-weight:bold;">{}</span></td>'.format(game_stats['visit'][a]['score'], game_stats['home'][a]['score'])
        if game_stats['homeTeam'].get('imageUrl'):
            logo = 'https://{}{}'.format(netloc, game_stats['homeTeam']['imageUrl'])
        else:
            logo = '{}/image?width=64&height=64'.format(config.server)
        content_html += '<td><img src="{}" style="width:64px;" /></td>'.format(logo)
        content_html += '<td><b>{}</b><br/><small>{}</small></td>'.format(game_stats['home']['name'], game_stats['home']['record'])
        content_html += '</tr></table>'

        content_html += '<table style="width:100%; border-collapse:collapse;">'
        content_html += '<tr><th>&nbsp;</th>'
        for it in game_stats['home'][a][b]:
            content_html += '<th style="text-align:center;">{}</th>'.format(it[c])
        content_html += '<th style="text-align:center;">F</th></tr>'

        content_html += '<tr><td style="padding:8px; border:1px solid black;">{}</td>'.format(game_stats['visit']['name'])
        for it in game_stats['visit'][a][b]:
            content_html += '<td style="text-align:center; border:1px solid black;">{}</td>'.format(it[d])
        content_html += '<td style="text-align:center; border:1px solid black;">{}</td></tr>'.format(game_stats['visit'][a]['score'], game_stats['visit']['name'])

        content_html += '<tr><td style="padding:8px; border:1px solid black;">{}</td>'.format(game_stats['home']['name'])
        for it in game_stats['home'][a][b]:
            content_html += '<td style="text-align:center; border:1px solid black;">{}</td>'.format(it[d])
        content_html += '<td style="text-align:center; border:1px solid black;">{}</td></tr>'.format(game_stats['home'][a]['score'])

        content_html += '</table>'
    else:
        content_html = '<table style="margin-left:auto; margin-right:auto;"><tr style="text-align:center; padding:8px;">'
        if game.get('dateUtc'):
            content_html += '<td colspan="5"><small>' + utils.format_display_date(datetime.fromisoformat(game['dateUtc']))
            if game.get('location'):
                content_html += ', ' + game['location']
            content_html += '</small></td><tr style="text-align:center; padding:8px;">'
        if game['locationIndicator'] == 'A':
            content_html += '<td><b>{}</b></td>'.format(team)
            logo = 'https://{}/images/logos/site/site.png'.format(netloc)
            content_html += '<td><img src="{}" style="width:64px;" /></td>'.format(logo)
            if game.get('result'):
                content_html += '<td style="text-align:center; padding:8px;"><span style="font-size:2em; font-weight:bold;">{}</span> {} <span style="font-size:2em; font-weight:bold;">{}</span></td>'.format(game['result']['teamScore'], game['atVs'], game['result']['opponentScore'])
            else:
                content_html += '<td style="text-align:center; padding:8px;"> {} </td>'.format(game['atVs'])
            if game['opponent'].get('image'):
                logo = 'https://{}{}'.format(netloc, game['opponent']['image']['fullpath'])
            else:
                logo = '{}/image?width=64&height=64'.format(config.server)
            content_html += '<td><img src="{}" style="width:64px;" /></td>'.format(logo)
            content_html += '<td style="text-align:center; padding:8px;"><b>{}</b></td>'.format(game['opponent']['title'])

        else:
            content_html += '<td style="text-align:center; padding:8px;"><b>{}</b></td>'.format(game['opponent']['title'])
            if game['opponent'].get('image'):
                logo = 'https://{}{}'.format(netloc, game['opponent']['image']['fullpath'])
            else:
                logo = '{}/image?width=64&height=64'.format(config.server)
            content_html += '<td><img src="{}" style="width:64px;" /></td>'.format(logo)
            if game.get('result'):
                content_html += '<td style="text-align:center; padding:8px;"><span style="font-size:2em; font-weight:bold;">{}</span> {} <span style="font-size:2em; font-weight:bold;">{}</span></td>'.format(game['result']['opponentScore'], game['atVs'], game['result']['teamScore'])
            else:
                content_html += '<td style="text-align:center; padding:8px;"> {} </td>'.format(game['atVs'])
            logo = 'https://{}/images/logos/site/site.png'.format(netloc)
            content_html += '<td><img src="{}" style="width:64px;" /></td>'.format(logo)
            content_html += '<td><b>{}</b></td>'.format(team)
        content_html += '</tr></table>'
    return content_html


def render_blocks(blocks, netloc, bg_color):
    content_html = ''
    for block in blocks:
        if block['type'] == 'basic_text_block':
            content_html += block['text']
        elif block['type'] == 'basic_image_block':
            img_src = 'https://{}{}'.format(netloc, block['image']['url'])
            content_html += utils.add_image(img_src, block['image'].get('caption'), link=block.get('url'))
        elif block['type'] == 'media_image_wall_block':
            content_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
            for image in block['images']:
                img_src = 'https://{}{}'.format(netloc, image['url'])
                content_html += '<div style="flex:1; min-width:360px;">{}</div>'.format(utils.add_image(img_src, image.get('caption')))
            content_html += '</div>'
        elif block['type'] == 'structural_layout_block':
            for content in block['content']:
                content_html += render_blocks(content, netloc, bg_color)
        elif block['type'] == 'basic_button_block':
            if block['url'].startswith('/'):
                link = 'https://{}{}'.format(netloc, block['url'])
            else:
                link = block['url']
            content_html += '<div style="line-height:2em; text-align:center;"><span style="padding:0.4em; font-weight:bold; background-color:{};"><a href="{}" style="color:white;">{}</a></span></div>'.format(bg_color, link, block['text'])
        else:
            logger.warning('unhandled content block type ' + block['type'])
    return content_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    netloc = split_url.netloc
    paths = list(filter(None, split_url.path.split('/')))
    m = re.search(r'/news/(\d+)/(\d+)/(\d+)', split_url.path)
    if not m:
        logger.warning('unhandled url ' + url)
        return None
    if paths[-1].endswith('.aspx'):
        slug = paths[-1][:-5]
    else:
        slug = paths[-1]
    api_url = 'https://{}/api/v2/stories/{}-{}-{}/{}'.format(netloc, m.group(2), m.group(3), m.group(1), slug)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    item = {}
    item['id'] = api_json['id']
    item['url'] = '{}://{}{}'.format(split_url.scheme, netloc, api_json['contentUrl'])
    item['title'] = api_json['contentTitle']

    dt = datetime.fromisoformat(api_json['contentDate']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {}
    if api_json.get('byline'):
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', api_json['byline'])
    else:
        item['author']['name'] = '{} Athletics'.format(site_json['team'])

    item['tags'] = []
    if api_json.get('sport'):
        item['tags'].append(api_json['sport']['title'])
    if api_json.get('players'):
        for it in api_json['players']:
            item['tags'].append('{} {}'.format(it['firstName'], it['lastName']))

    if api_json.get('imageSource'):
        item['_image'] = 'https://{}{}'.format(netloc, api_json['imageSource'])

    if api_json.get('teaser'):
        item['summary'] = api_json['teaser']

    item['content_html'] = ''
    if api_json.get('games'):
        for game in api_json['games']:
            item['content_html'] += add_game_stats(game, api_json['globalSportMapName'], netloc, site_json['team'])

    if api_json.get('video') and api_json['video'].get('archive'):
        item['content_html'] += add_video(api_json['video']['archive'], netloc)
    elif item.get('_image'):
        captions = []
        if api_json.get('imageCaption'):
            captions.append(api_json['imageCaption'])
        if api_json.get('imageCreditText'):
            captions.append(api_json['imageCreditText'])
        if api_json.get('redirectAbsoluteUrl'):
            link = api_json['redirectAbsoluteUrl']
        else:
            link = ''
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions), link=link)

    if api_json.get('content'):
        if not api_json['content'].startswith('<p'):
            item['content_html'] += '<div>&nbsp;</div>'
        item['content_html'] += api_json['content']
        def sub_iframe(match_obj):
            return utils.add_embed(match_obj.group(1)) + '<div>&nbsp;</div>'
        item['content_html'] = re.sub(r'<iframe[^>]+src="([^"]+)"[^>]*>.*?</iframe>', sub_iframe, item['content_html'])
        def sub_image(match_obj):
            nonlocal netloc
            if match_obj.group(1).startswith('/'):
                img_src = 'https://' + netloc + match_obj.group(1)
            else:
                img_src = match_obj.group(1)
            return utils.add_image(img_src)
        item['content_html'] = re.sub(r'<div[^>]+sidearm-story-image[^>]+><img[^>]+src="([^"]+)"[^>]*>.*?</div>', sub_image, item['content_html'])
    elif api_json.get('blocks'):
        item['content_html'] += render_blocks(api_json['blocks'], netloc, site_json['bg_color'])

    item['content_html'] = re.sub(r'href="(/[^"]+)"', r'href="https://{}\1"'.format(netloc), item['content_html'])
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    feed_title = ''
    if 'rss' in paths:
        return rss.get_feed(url, args, site_json, save_debug, get_content)
    elif paths[0] == 'sports':
        sports = utils.get_url_json('https://{}/api/v2/Sports'.format(split_url.netloc))
        if not sports:
            return None
        sport = next((it for it in sports if it['globalSportNameSlug'] == paths[1]), None)
        if not sport:
            logger.warning('unknown sport in ' + url)
            return None
        #api_url = 'https://{}/services/adaptive_components.ashx?type=stories&count=10&start=0&sport_id={}&extra=%7B%7D'.format(split_url.netloc, sport['id'])
        api_url = 'https://{}/api/v2/stories?sportId={}'.format(split_url.netloc, sport['id'])
        feed_title = '{} {}'.format(site_json['team'], sport['title'])
    elif paths[0] == 'archives':
        query = parse_qs(split_url.query)
        if query.get('path'):
            sports = utils.get_url_json('https://{}/api/v2/Sports'.format(split_url.netloc))
            if not sports:
                return None
            sport = next((it for it in sports if it['shortName'] == query['path'][0]), None)
            if not sport:
                logger.warning('unknown sport in ' + url)
                return None
            api_url = 'https://{}/api/v2/stories?sportId={}'.format(split_url.netloc, sport['id'])
            feed_title = '{} {}'.format(site_json['team'], sport['title'])
        else:
            api_url = 'https://{}/api/v2/stories'.format(split_url.netloc)
            feed_title = '{} Athletics'.format(site_json['team'])

    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None

    n = 0
    feed_items = []
    for story in api_json['items']:
        story_url = 'https://{}{}'.format(split_url.netloc, story['contentUrl'])
        if save_debug:
            logger.debug('getting content for ' + story_url)
        item = get_content(story_url, args, site_json, save_debug)
        if item:
          if utils.filter_item(item, args) == True:
            feed_items.append(item)
            n += 1
            if 'max' in args:
                if n == int(args['max']):
                    break
    feed = utils.init_jsonfeed(args)
    if feed_title:
        feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
