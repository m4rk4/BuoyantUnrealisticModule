import base64, json, pytz, re, requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit, quote_plus

import config, utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1024):
    if img_src.startswith('https://cdn-media.theathletic.com/cdn-cgi/image/'):
        return re.sub(r'(width=\d+)', 'width={}'.format(width), img_src)
    else:
        return 'https://cdn-media.theathletic.com/cdn-cgi/image/width={}%2cformat=auto%2cquality=75/{}'.format(width, img_src)


def get_next_data(url):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', id='__NEXT_DATA__')
    if not el:
        logger.warning('unable to find __NEXT_DATA__ in ' + url)
        return None
    return json.loads(base64.urlsafe_b64decode(el.string))


def get_podcast_clip(url, args, site_json, save_debug):
    # This is basic and only for embeds
    # https://theathletic.com/report/podcast-clip?clip_id=5661
    s = requests.session()
    r = s.get(url)
    if r.status_code != 200:
        return None
    if save_debug:
        utils.write_file(r.text, './debug/debug.html')
    soup = BeautifulSoup(r.text, 'html.parser')

    item = {}
    el = soup.find(id='preview-clip')
    item['id'] = el['data-episode-id']

    el = soup.find(class_='podcast-episode-title')
    item['title'] = el.get_text()

    for el in soup.find_all(class_='embed-podcast-left-pad'):
        if 'row' in el['class']:
            continue
        for it in el.find_all('a'):
            if 'episode=' in it['href']:
                ep_url = it['href']
                item['summary'] = it.get_text()
            else:
                show_url = it['href']
                item['author'] = {"name": it.get_text()}
        break

    el = soup.find(class_='show-small-embed-podcast-image')
    it = el.find('img')
    item['_image'] = it['src']
    poster = '{}/image?url={}&width=128&overlay=audio'.format(config.server, quote_plus(item['_image']))

    post_data = {"action": "podcast-episode-clip", "podcast_episode_id": 28656}
    post = s.post('https://theathletic.com/web-api', post_data)
    if post.status_code == 200:
        post_json = post.json()
        audio_url = post_json['audio_url']
    else:
        audio_url = ep_url
    item['content_html'] = '<table><tr><td><a href="{}"><img src="{}"/></a></td><td style="vertical-align:top;"><h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small><a href="{}">{}</a><br/>{}</small></td></tr></table>'.format(audio_url, poster, ep_url, item['title'], show_url, item['author']['name'], item['summary'])
    return item

def get_podcast_episode_clip(episode_id):
    post_data = {"action": "podcast-episode-clip", "podcast_episode_id": int(episode_id)}
    post = requests.post('https://theathletic.com/web-api', post_data)
    if post.status_code == 200:
        # utils.write_file(audio_json, './debug/audio.json')
        audio_json = post.json()
        if 'error' not in audio_json:
            return audio_json
    return None


def get_podcast_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url)
    if save_debug:
        utils.write_file(next_data, './debug/next.json')
    podcast_json = next_data['props']['pageProps']['podcast']
    m = re.search(r'episode-(\d+)', url)
    if m:
        ep_number = int(m.group(1))
        episode = next((it for it in podcast_json['episodes'] if it['number'] == ep_number), None)
        if episode:
            item = {}
            item['id'] = episode['id']
            item['url'] = episode['permalink']
            item['title'] = episode['title']
            tz_est = pytz.timezone('US/Eastern')
            dt_est = datetime.fromtimestamp(episode['published_at'] / 1000)
            dt = tz_est.localize(dt_est).astimezone(pytz.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt, date_only=True)
            item['author'] = {
                "name": podcast_json['title'],
                "url": podcast_json['permalink_url']
            }
            item['authors'] = []
            item['authors'].append(item['author'])
            item['image'] = podcast_json['image_url']
            item['summary'] = episode['description']
            clip_json = get_podcast_episode_clip(episode['id'])
            if clip_json:
                item['_audio'] = clip_json['audio_url']
                attachment = {}
                attachment['url'] = item['_audio']
                attachment['mime_type'] = 'audio/mpeg'
                item['attachments'] = []
                item['attachments'].append(attachment)
            else:
                logger.warning('unable to get podcast episode clip for ' + item['url'])
                item['_audio'] = None
            # The clip url will expire, so link it dynamically
            audio_src = config.server + '/audio?url=' + quote_plus(item['url'])
            item['content_html'] = utils.add_audio(audio_src, item['image'], item['title'], item['url'], item['author']['name'], item['author']['url'], item['_display_date'], episode['duration'])
            if 'embed' not in args:
                item['content_html'] += '<p>' + item['summary'] + '</p>'
            return item

    item = {}
    item['id'] = podcast_json['id']
    item['url'] = podcast_json['permalink_url']
    item['title'] = podcast_json['title']
    item['author'] = {
        "name": podcast_json['title'],
        "url": podcast_json['permalink_url']
    }
    item['authors'] = []
    item['authors'].append(item['author'])
    item['image'] = podcast_json['image_url']
    item['summary'] = podcast_json['description']
    item['content_html'] = '<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:8px; margin:8px;">'
    item['content_html'] += '<div style="flex:1; min-width:128px; max-width:160px;"><a href="{}" target="_blank"><img src="{}" style="width:100%;"/></a></div>'.format(item['url'], item['image'])
    item['content_html'] += '<div style="flex:2; min-width:256px;"><div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div><div style="margin:4px 0 4px 0; font-size:0.8em;">{}</div></div>'.format(item['url'], item['title'], item['summary'])
    item['content_html'] += '</div><h3>Episodes:</h3>'
    for episode in podcast_json['episodes'][:5]:
        tz_est = pytz.timezone('US/Eastern')
        dt_est = datetime.fromtimestamp(episode['published_at'] / 1000)
        dt = tz_est.localize(dt_est).astimezone(pytz.utc)
        if 'date_published' not in item:
            # Should be most recent first
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt, date_only=True)
        audio_src = config.server + '/audio?url=' + quote_plus(episode['permalink'])
        item['content_html'] += utils.add_audio(audio_src, '', episode['title'], episode['permalink'], '', '', utils.format_display_date(dt, date_only=True), episode['duration'], use_video_js=False)
    return item


def get_content(url, args, site_json, save_debug=False):
    if '/podcast/' in url:
        return get_podcast_content(url, args, site_json, save_debug)

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))

    if 'live-blogs' in paths:
        post_data = {
            "operationName": "",
            "variables": {
                "postsPage": 0,
                "postsPerPage": 20,
                "includeAds": True,
                "id": paths[-1]
            },
            "query": "\n  query GetLiveBlogFull(\n    $id: ID!\n    $postsPage: Int = 0\n    $postsPerPage: Int = 100\n    $includeAds: Boolean = false\n    $initialPostId: ID\n  ) {\n    liveBlog(id: $id) {\n      ad_unit_path\n      ad_targeting_params {\n        auth\n        byline\n        coll\n        id\n        keywords\n        org\n        tags\n        typ\n      }\n      byline_linkable {\n        ... on LinkableString {\n          raw_string\n          web_linked_string\n        }\n      }\n      byline_authors {\n        avatar_uri\n        name\n      }\n      createdAt\n      description\n      game_id\n      is_unlocked\n      free_apron_state\n      id\n      images {\n        credits\n        imageCdnUri: image_cdn_uri\n        imageHeight: image_height\n        imageUri: image_uri\n        imageWidth: image_width\n      }\n      lastActivityAt\n      match_widgets\n      metadata {\n        about {\n          endDate\n          startDate\n        }\n      }\n      posts(\n        page: $postsPage\n        perPage: $postsPerPage\n        sort: { direction: desc, field: \"published_at\" }\n        includeAds: $includeAds\n        initialPostId: $initialPostId\n      ) {\n        items {\n          ... on LiveBlogPost {\n            permalink\n            attachments {\n              html\n              id\n              image_uri\n              short_title\n              title\n              type\n              url\n            }\n            articles {\n              id\n              permalink\n              short_title\n              title\n              imageUri: image_uri\n            }\n            body\n            createdAt\n            id\n            images {\n              alt_text\n              credits\n              imageCdnUri: image_cdn_uri\n              image_height\n              image_width\n            }\n            is_pinned\n            publishedAt\n            title\n            tweets: tweetsv2 {\n              html\n              url\n            }\n            type\n            updatedAt\n            user {\n              id\n              name\n              ... on Staff {\n                avatarUri: avatar_uri\n                fullDescription: full_description\n                slug\n              }\n            }\n          }\n          ... on LiveBlogDropzone {\n            dropzone_id\n            id\n            type\n          }\n        }\n        pageInfo {\n          currentPage\n          hasNextPage\n          hasPreviousPage\n        }\n        total\n        numNewPosts\n      }\n      permalink\n      primaryLeague {\n        shortname\n      }\n      publishedAt\n      short_title\n      slug\n      status\n      tags {\n        id\n        name\n        shortname\n        type\n      }\n      title\n      tweets: tweetsv2 {\n        html\n        url\n      }\n      type\n      updatedAt\n    }\n  }\n"
        }
    else:
        post_data = {
            "operationName": "ArticleViewQuery",
            "variables": {
                "id": paths[1]
            },
            "query": "\n  query ArticleViewQuery(\n    $id: ID!\n    $is_preview: Boolean = false\n    $prop: String = \"\"\n    $is_mobile: Boolean = true\n    $is_desktop: Boolean = false\n  ) {\n    articleById(id: $id, is_preview: $is_preview) {\n      ...article\n    }\n  }\n\n  fragment article on Article {\n    ad_unit_path\n    ad_targeting_params(prop: $prop) {\n      auth\n      byline\n      coll\n      id\n      keywords\n      org\n      tags\n      typ\n      prop\n      gscat\n      als_test_clientside\n      tt\n    }\n    article_body\n    article_body_desktop @include(if: $is_desktop)\n    article_body_mobile @include(if: $is_mobile)\n    authors {\n      author {\n        ... on Staff {\n          avatar_uri\n          bio\n          role\n          slug\n          twitter\n        }\n        first_name\n        name\n        id\n      }\n    }\n    byline_linkable {\n      ... on LinkableString {\n        raw_string\n        web_linked_string\n      }\n    }\n    chartbeat_authors {\n      author {\n        id\n        name\n        ... on Staff {\n          slug\n        }\n      }\n    }\n    chartbeat_sections\n    comment_count\n    disable_comments\n    entity_keywords\n    excerpt\n    featured\n    hide_scores_banner\n    hide_upsell_text\n    id\n    image_uri\n    image_uri_full\n    image_caption\n    inferred_league_ids\n    is_teaser\n    is_premier\n    is_hard_regwall\n    is_paid_post\n    is_unpublished\n    last_activity_at\n    league_ids\n    league_urls\n    lock_comments\n    news_topics\n    permalink\n    post_type_id\n    primary_tag\n    primary_league\n    primary_league_details {\n      sport_type\n      shortname\n      url\n      id\n    }\n    published_at\n    short_title\n    subscriber_score\n    team_hex\n    team_ids\n    team_urls\n    title\n  }\n"
        }
    headers = {
        "accept": "*/*",
        "accept-language": "null",
        "apollographql-client-name": "web",
        "apollographql-client-version": "1.0",
        "content-type": "application/json",
        "priority": "u=1, i",
        "sec-ch-ua": "\"Chromium\";v=\"128\", \"Not;A=Brand\";v=\"24\", \"Microsoft Edge\";v=\"128\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site"
    }
    gql_json = utils.post_url('https://api.theathletic.com/graphql', json_data=post_data, headers=headers)
    article_json = None
    if gql_json:
        if save_debug:
            utils.write_file(gql_json, './debug/debug.json')
        if 'live-blogs' in paths:
            article_json = gql_json['data']['liveBlog']
        else:
            article_json = gql_json['data']['articleById']

    if not article_json:
        logger.debug('getting __NEXT_DATA__ from ' + url)
        next_data = get_next_data(url)
        if next_data:
            if save_debug:
                utils.write_file(next_data, './debug/next.json')
            if next_data['props']['pageProps'].get('article'):
                article_json = next_data['props']['pageProps']['article']

    if not article_json:
        logger.waring('unhandled article ' + url)
        return None

    # if save_debug:
    #     utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['permalink']
    item['title'] = article_json['title']

    tz_est = pytz.timezone('US/Eastern')
    if article_json.get('published_at'):
        dt_est = datetime.fromtimestamp(article_json['published_at'] / 1000)
    elif article_json.get('publishedAt'):
        dt_est = datetime.fromtimestamp(article_json['publishedAt'] / 1000)
    dt = tz_est.localize(dt_est).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if article_json.get('last_activity_at'):
        dt_est = datetime.fromtimestamp(article_json['last_activity_at'] / 1000)
    elif article_json.get('lastActivityAt'):
        dt_est = datetime.fromtimestamp(article_json['lastActivityAt'] / 1000)
    dt = tz_est.localize(dt_est).astimezone(pytz.utc)
    item['date_modified'] = dt.isoformat()

    # Check age
    if 'age' in args:
        if not utils.check_age(item, args):
            return None

    item['authors'] = []
    if article_json.get('authors'):
        for it in article_json['authors']:
            item['authors'].append({"name": it['author']['name']})
    elif article_json.get('byline_authors'):
        for it in article_json['byline_authors']:
            item['authors'].append({"name": it['name']})
    elif article_json.get('chartbeat_authors'):
        for it in article_json['chartbeat_authors']:
            item['authors'].append({"name": it['author']['name']})
    else:
        item['authors'].append({"name": "The Athletic Staff"})
    if article_json.get('byline_linkable') and article_json['byline_linkable'].get('raw_string'):
        byline = article_json['byline_linkable']['raw_string']
        for it in item['authors']:
            byline = byline.replace(it['name'], '')
        byline = byline.replace(',', '').replace('and', '').strip()
        if byline:
            item['authors'].append({"name": byline})
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = []
    if article_json.get('entity_keywords'):
        for tag in re.findall(r'([^,]+)(,|$)\s?', article_json['entity_keywords']):
            if tag[0] not in item['tags']:
                item['tags'].append(tag[0])
    if article_json.get('chartbeat_sections'):
        for tag in re.findall(r'([^,]+)(,|$)\s?', article_json['chartbeat_sections']):
            if tag[0] not in item['tags']:
                item['tags'].append(tag[0])
    if article_json.get('tags'):
        for tag in article_json['tags']:
            if tag.get('name'):
                item['tags'].append(tag['name'])
            if tag.get('shortname'):
                item['tags'].append(tag['shortname'])
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''

    if article_json.get('game_id'):
        post_data = {
            "operationName": "GetGameForLiveBlog",
            "variables": {
                "id": article_json['game_id']
            },
            "query": "\n  query GetGameForLiveBlog($id: ID!, $show_sidebar: Boolean = false) {\n    game(id: $id) {\n      ad_targeting_params {\n        auth\n        byline\n        coll\n        org\n        id\n        tags\n        keywords\n        typ\n      }\n      id\n      game_title\n      status\n      started_at\n      time_tbd\n      scheduled_at\n      sport\n      match_time_display\n      finished_at\n      league {\n        id\n        slug\n        current_season {\n          starts_at\n          finishes_at\n        }\n      }\n      away_team {\n        score\n        current_standing\n        team {\n          id\n          display_name\n          alias\n          logos {\n            uri\n          }\n        }\n      }\n      home_team {\n        score\n        current_standing\n        team {\n          id\n          display_name\n          alias\n          logos {\n            uri\n          }\n        }\n      }\n      venue {\n        city\n        name\n        state\n      }\n      ...AmericanFootballGameLiveBlog\n      ...BaseballGameLiveBlog\n      ...BasketballGameLiveBlog\n      ...HockeyGameLiveBlog\n      ...SoccerGameHeader @skip(if: $show_sidebar)\n      ...SoccerGameLiveBlogSidebar @include(if: $show_sidebar)\n    }\n  }\n  \n  fragment AmericanFootballGameLiveBlog on AmericanFootballGame {\n    broadcast_network\n    period_id\n    period\n    clock\n    possession {\n      team {\n        id\n      }\n    }\n\n    away_team {\n      ...AmericanFootballGameTeamLiveBlog\n    }\n    home_team {\n      ...AmericanFootballGameTeamLiveBlog\n    }\n  }\n\n  fragment AmericanFootballGameTeamLiveBlog on AmericanFootballGameTeam {\n    current_ranking\n    team {\n      logos {\n        height\n        width\n      }\n    }\n    used_timeouts\n    remaining_timeouts\n  }\n\n  fragment BaseballGameLiveBlog on BaseballGame {\n    broadcast_network\n    inning\n    inning_half\n    period_id\n    outcome {\n      balls\n      outs\n      strikes\n      runners {\n        ending_base\n      }\n    }\n\n    away_team {\n      ...BaseballGameTeamLiveBlog\n    }\n    home_team {\n      ...BaseballGameTeamLiveBlog\n    }\n  }\n\n  fragment BaseballGameTeamLiveBlog on BaseballGameTeam {\n    team {\n      logos {\n        height\n        width\n      }\n    }\n  }\n\n  fragment BasketballGameLiveBlog on BasketballGame {\n    broadcast_network\n    period_id\n    clock\n    away_team {\n      ...BasketballGameTeamLiveBlog\n    }\n    home_team {\n      ...BasketballGameTeamLiveBlog\n    }\n  }\n\n  fragment BasketballGameTeamLiveBlog on BasketballGameTeam {\n    current_ranking\n    team {\n      logos {\n        height\n        width\n      }\n    }\n    remaining_timeouts\n    used_timeouts\n  }\n\n  fragment HockeyGameLiveBlog on HockeyGame {\n    broadcast_network\n    period_id\n    clock\n    away_team {\n      ...HockeyGameTeamLiveBlog\n    }\n    home_team {\n      ...HockeyGameTeamLiveBlog\n    }\n  }\n\n  fragment HockeyGameTeamLiveBlog on HockeyGameTeam {\n    strength\n    team {\n      logos {\n        height\n        width\n      }\n    }\n  }\n\n  fragment SoccerGameHeader on SoccerGame {\n    id\n    ad_targeting_params {\n      auth\n      byline\n      coll\n      org\n      id\n      tags\n      keywords\n      typ\n    }\n    ad_unit_path\n    aggregate_winner {\n      alias\n    }\n    away_team {\n      ...SoccerGameTeamHeader\n    }\n    coverage {\n      available_data\n    }\n    game_title\n    home_team {\n      ...SoccerGameTeamHeader\n    }\n    key_events {\n      ... on CardEvent {\n        card_type\n        carded_player {\n          id\n          display_name\n        }\n      }\n      ... on GoalEvent {\n        goal_type\n        goal_scorer {\n          id\n          display_name\n        }\n      }\n      ... on SubstitutionEvent {\n        player_on {\n          id\n          display_name\n        }\n        player_off {\n          id\n          display_name\n        }\n      }\n      match_time\n      match_time_display\n      team {\n        id\n      }\n      __typename\n    }\n    league {\n      id\n      legacy_id\n      name\n      slug\n    }\n    leg\n    live_blog {\n      id\n      permalink\n    }\n    match_time_display\n    scheduled_at\n    sport\n    started_at\n    status\n    time_tbd\n  }\n\n  fragment SoccerGameTeamHeader on SoccerGameTeam {\n    id\n    aggregate_score\n    current_record\n    current_standing\n    current_standing_short: current_standing(short: true)\n    expected_goals {\n      decimal_value\n    }\n    line_up {\n      manager_id\n    }\n    penalty_score\n    score\n    team {\n      id\n      alias\n      color_contrast\n      legacy_team {\n        id\n        league_id\n        url\n      }\n      logo\n      name\n    }\n  }\n\n  fragment SoccerGameLiveBlogSidebar on SoccerGame {\n    ...SoccerGameHeader\n    away_team {\n      ...SoccerGameTeamGameTab\n    }\n    finished_at\n    home_team {\n      ...SoccerGameTeamGameTab\n    }\n    league {\n      display_name\n    }\n    officials {\n      id\n      name\n      type\n    }\n    season_stats {\n      ...GameSeasonStats\n    }\n    season_type {\n      id\n    }\n    tickets {\n      ...GameTickets\n    }\n    title\n    venue {\n      city\n      name\n      state\n    }\n  }\n\n  fragment SoccerGameTeamGameTab on SoccerGameTeam {\n    last_games(size: 5, game_league_only: true) {\n      ... on SoccerGame {\n        aggregate_winner {\n          alias\n        }\n        leg\n      }\n      id\n      away_team {\n        aggregate_score\n        penalty_score\n        score\n        team {\n          id\n          alias\n          display_name\n          league {\n            is_primary\n            slug\n          }\n          legacy_team {\n            url\n          }\n          logos {\n            height\n            uri\n            width\n          }\n          name\n        }\n      }\n      game_title\n      home_team {\n        aggregate_score\n        penalty_score\n        score\n        team {\n          id\n          alias\n          display_name\n          league {\n            is_primary\n            slug\n          }\n          legacy_team {\n            url\n          }\n          logos {\n            height\n            uri\n            width\n          }\n          name\n        }\n      }\n      league {\n        slug\n      }\n      match_time_display\n      scheduled_at\n      sport\n    }\n    last_six\n    line_up {\n      id\n      formation\n      image_uri\n      manager\n      players {\n        id\n        captain\n        display_name\n        jersey_number\n        player {\n          id\n          slug\n        }\n        position\n        regular_position\n        starter\n        stats {\n          stat_label\n          stat_type\n          ... on DecimalGameStat {\n            decimal_value\n            string_value\n          }\n          ... on FractionGameStat {\n            denominator_value\n            numerator_value\n            string_value\n          }\n          ... on IntegerGameStat {\n            int_value\n            string_value\n          }\n          ... on PercentageGameStat {\n            decimal_value\n            string_value\n          }\n          ... on StringGameStat {\n            string_value\n          }\n        }\n      }\n    }\n    stat_leaders {\n      id\n      player {\n        id\n        display_name\n        headshots {\n          height\n          uri\n          width\n        }\n        jersey_number\n        position\n        slug\n      }\n      stats {\n        id\n        __typename\n        stat_category\n        stat_header_label\n        stat_label\n        stat_type\n        ... on DecimalGameStat {\n          decimal_value\n          string_value\n        }\n        ... on FractionGameStat {\n          denominator_value\n          numerator_value\n          string_value\n        }\n        ... on IntegerGameStat {\n          int_value\n          string_value\n        }\n        ... on PercentageGameStat {\n          decimal_value\n          string_value\n        }\n        ... on StringGameStat {\n          string_value\n        }\n        ... on TimeGameStat {\n          hours_value\n          minutes_value\n          seconds_value\n          string_value\n        }\n      }\n      stats_label\n    }\n    stats {\n      __typename\n      stat_category\n      stat_label\n      stat_type\n      ... on DecimalGameStat {\n        decimal_value\n        less_is_best\n        reference_only\n        string_value\n      }\n      ... on FractionGameStat {\n        denominator_value\n        numerator_value\n        less_is_best\n        reference_only\n        string_value\n      }\n      ... on IntegerGameStat {\n        int_value\n        less_is_best\n        reference_only\n        string_value\n      }\n      ... on PercentageGameStat {\n        decimal_value\n        less_is_best\n        reference_only\n        string_value\n      }\n      ... on StringGameStat {\n        string_value\n      }\n    }\n    team {\n      color_primary\n      display_name\n      injuries {\n        comment\n        injury\n        player {\n          id\n          display_name\n          headshots {\n            height\n            uri\n            width\n          }\n          position\n          slug\n        }\n        status\n      }\n      league {\n        slug\n      }\n      logos {\n        height\n        uri\n        width\n      }\n      slug\n    }\n  }\n\n  fragment GameSeasonStats on GameSeasonStats {\n    away_stat_leaders {\n      ...TeamLeader\n    }\n    away_team_stats {\n      parent_stat_type\n      rank\n      stat_label\n      stat_value\n    }\n    home_stat_leaders {\n      ...TeamLeader\n    }\n    home_team_stats {\n      parent_stat_type\n      rank\n      stat_label\n      stat_value\n    }\n    season {\n      id\n      name\n      active\n    }\n    season_type {\n      name\n    }\n  }\n\n  fragment GameTickets on GameTickets {\n    logos_light_mode {\n      id\n      height\n      uri\n      width\n    }\n    min_price {\n      amount\n      currency\n    }\n    provider\n    uri\n  }\n\n  fragment TeamLeader on TeamLeader {\n    id\n    player {\n      id\n      display_name\n      headshots {\n        height\n        uri\n        width\n      }\n      jersey_number\n      position\n      slug\n    }\n    stats {\n      id\n      __typename\n      stat_category\n      stat_header_label\n      stat_label\n      stat_type\n      ... on DecimalGameStat {\n        decimal_value\n        string_value\n      }\n      ... on FractionGameStat {\n        denominator_value\n        numerator_value\n        string_value\n      }\n      ... on IntegerGameStat {\n        int_value\n        string_value\n      }\n      ... on PercentageGameStat {\n        decimal_value\n        string_value\n      }\n      ... on StringGameStat {\n        string_value\n      }\n      ... on TimeGameStat {\n        hours_value\n        minutes_value\n        seconds_value\n        string_value\n      }\n    }\n    stats_label\n  }\n"
        }
        gql_json = utils.post_url('https://api.theathletic.com/graphql', json_data=post_data, headers=headers)
        if gql_json:
            if save_debug:
                utils.write_file(gql_json, './debug/game.json')
            game_json = gql_json['data']['game']
            item['content_html'] += '<table style="margin:auto;"><tr><td colspan="3" style="text-align:center; font-size:0.8em;">' + game_json['league']['name']
            if game_json.get('game_title'):
                item['content_html'] += ', ' + game_json['game_title']
            item['content_html'] += '</td></tr>'
            item['content_html'] += '<tr><td colspan="3" style="text-align:center; font-size:0.8em;">{}, {}</td></tr>'.format(game_json['venue']['name'], game_json['venue']['city'])
            tz_loc = pytz.timezone(config.local_tz)
            dt_loc = datetime.fromtimestamp(game_json['scheduled_at'] / 1000)
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
            item['content_html'] += '<tr><td colspan="3" style="text-align:center; font-size:0.8em;">{}</td></tr>'.format(utils.format_display_date(dt))
            for x in ['away_team', 'home_team']:
                team = game_json[x]
                item['content_html'] += '<tr><td><img src="{}" style="width:64px;"/></td><td style="text-align:left; font-size:1.5em; font-weight:bold;">{}</td><td style="text-align:center; font-size:2em; font-weight:bold;">'.format(team['team']['logo'], team['team']['display_name'])
                if game_json['status'] == 'scheduled':
                    item['content_html'] += '&ndash;'
                else:
                    item['content_html'] += str(team['score'])
                item['content_html'] += '</td></tr>'
            if game_json['status'] == 'final':
                dt_loc = datetime.fromtimestamp(game_json['finished_at'] / 1000)
                dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
                item['content_html'] += '<tr><td colspan="3" style="text-align:center;">Final - {}</td></tr>'.format(utils.format_display_date(dt))
            # elif game_json['status'] == 'in_progress' and game_json.get('game_status'):
            #     item['content_html'] += '<tr><td colspan="3" style="text-align:center;">' + game_json['game_status']['main']
            #     if game_json['game_status'].get('extra'):
            #         item['content_html'] += ', ' + game_json['game_status']['extra']
            #     item['content_html'] += '</td></tr>'
            elif game_json.get('match_time_display'):
                item['content_html'] += '<tr><td colspan="3" style="text-align:center;">{}</td></tr>'.format(game_json['match_time_display'])
            item['content_html'] += '</table>'

    if article_json.get('excerpt'):
        item['summary'] = article_json['excerpt']
    elif article_json.get('description'):
        item['summary'] = article_json['description']
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    if article_json.get('image_uri'):
        item['image'] = resize_image(article_json['image_uri'])
        item['content_html'] += utils.add_image(item['image'], article_json['image_caption'])
    elif article_json.get('images'):
        item['image'] = resize_image(article_json['images'][0]['imageCdnUri'])
        item['content_html'] += utils.add_image(item['image'], article_json.get('credits'))

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if article_json.get('article_body_desktop'):
        soup = BeautifulSoup(article_json['article_body_desktop'], 'html.parser')
        # item['content_html'] += wp_posts.format_content(article_json['article_body_desktop'], item, site_json)
    elif article_json.get('article_body'):
        soup = BeautifulSoup(article_json['article_body'], 'html.parser')
        # item['content_html'] += wp_posts.format_content(article_json['article_body'], item, site_json)
    if soup:
        if save_debug:
            utils.write_file(str(soup), './debug/debug.html')

        for el in soup.find_all(class_='embed-article'):
            el.decompose()

        for el in soup.find_all(class_='wp-caption', recursive=False):
            img_src = ''
            it = el.find('img')
            if it:
                if it.get('srcset'):
                    img_src = utils.image_from_srcset(it['srcset'], 1200)
                elif it.get('src'):
                    img_src = it['src']
            if img_src:
                it = el.find('a')
                if it:
                    link = it['href']
                else:
                    link = ''
                it = el.find(class_='credits-text')
                if it:
                    caption = it.decode_contents()
                else:
                    caption = ''
                new_html = utils.add_image(img_src, caption, link=link)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled wp-caption in ' + item['url'])

        for el in soup.find_all(attrs={"data-ath-video-stream": True}, recursive=False):
            it = el.find(attrs={"data-type": "application/x-mpegURL"})
            if not it:
                it = el.find(attrs={"data-type": "application/dash+xml"})
            if it:
                paths = list(filter(None, urlsplit(it['data-source']).path[1:].split('/')))
                i = paths.index(el['data-ath-video-stream'])
                poster = 'https://cdn-media.theathletic.com/video-stream/auto-thumbnail/' + paths[i] + '/' + paths[i + 1] + '.0000000.jpg'
                new_html = utils.add_video(it['data-source'], it['data-type'], poster)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)

        for el in soup.find_all(id='inline-graphic'):
            if el.find(class_='showcase-link-container'):
                el.decompose()
            elif el.find('iframe'):
                it = el.find('iframe')
                new_html = utils.add_embed(it['src'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                if el.parent and el.parent.name == 'div':
                    el.parent.replace_with(new_el)
                else:
                    el.replace_with(new_el)
            else:
                logger.warning('unhandled inline-graphic in ' + item['url'])

        for el in soup.find_all(class_='instagram-media'):
            links = el.find_all('a')
            new_html = utils.add_embed(links[-1]['href'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

        for el in soup.find_all(class_='twitter-tweet'):
            new_html = utils.add_embed(el['data-instgrm-permalink'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

        item['content_html'] += str(soup)

    if article_json.get('posts') and article_json['posts'].get('items'):
        for i, post in enumerate(article_json['posts']['items']):
            if post['type'] == 'liveBlogPost':
                if i > 0:
                    item['content_html'] += '<div>&nbsp;</div><hr/>'
                dt_est = datetime.fromtimestamp(post['updatedAt'] / 1000)
                dt = tz_est.localize(dt_est).astimezone(pytz.utc)
                if post['user'].get('avatarUri'):
                    item['content_html'] += '<div>&nbsp;</div><div><img src="{}" style="float:left; margin-right:8px; height:2.5em; border-radius:50%;"></div>'.format(post['user']['avatarUri'])
                else:
                    item['content_html'] += '<div>&nbsp;</div><div><img src="https://cdn.theathletic.com/app/uploads/2016/07/08183138/ta_avatar.png" style="float:left; margin-right:8px; height:2.5em; border-radius:50%;"></div>'.format(post['user']['avatarUri'])
                item['content_html'] += '<div style="font-size:0.8em; margin-bottom:4px;"><a href="{}">{}</a></div>'.format(post['permalink'], utils.format_display_date(dt))
                item['content_html'] += '<div><a href="https://www.nytimes.com/athletic/author/{}/">{}</a>'.format(post['user']['slug'], post['user']['name'], post['user']['fullDescription'])
                if post['user'].get('fullDescription'):
                    item['content_html'] += ' &bull; <small>{}</small>'.format(post['user']['fullDescription'])
                item['content_html'] += '</div><div style="clear:left;"></div>'
                if post.get('title'):
                    item['content_html'] += '<h3>{}</h3>'.format(post['title'])
                for it in post['images']:
                    item['content_html'] += utils.add_image(resize_image(it['imageCdnUri']), it.get('credits'))
                if post.get('body'):
                    item['content_html'] += post['body']
                for it in post['attachments']:
                    if it['type'] == 'article':
                        item['content_html'] += utils.add_embed(it['url'])
                    elif it['type'] == 'twitter':
                        item['content_html'] += utils.add_embed(it['url'])
                    else:
                        logger.warning('unhandled liveBlogPost attachment type {} in {}'.format(it['type'], item['url']))

    item['content_html'] = item['content_html'].replace(' class="ath_autolink"', '')
    item['content_html'] = item['content_html'].replace('<span class="Apple-converted-space">\u00a0</span>', '&nbsp;')
    return item


def get_feed(url, args, site_json, save_debug=False):
    if 'rss' not in args['url']:
        logger.warning('unhandled feed url ' + url)
        return None
    return rss.get_feed(url, args, site_json, save_debug, get_content)
