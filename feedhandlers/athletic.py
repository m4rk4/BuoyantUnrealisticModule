import json, pytz, re, requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit, quote_plus

import config, utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    m = re.search(r'(\/width=\d+\/)', img_src)
    if m:
        img_src = img_src.replace(m.group(1), '/width={}/'.format(width))
    elif img_src.startswith('https://cdn.theathletic.com/app/uploads/'):
        img_src = img_src.replace('https://cdn.theathletic.com/',
                                  'https://cdn.theathletic.com/cdn-cgi/image/width={}/'.format(width))
    return img_src


def get_next_data(url):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', id='__NEXT_DATA__')
    if not el:
        logger.warning('unable to find __NEXT_DATA__ in ' + url)
        return None
    return json.loads(el.string)


def get_news_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    post_data = {"query": "\n  query NewsItemPage($id: ID!) {\n    newsById(id: $id, version: current) {\n      byline\n      byline_linkable {\n        ... on LinkableString {\n          raw_string\n          web_linked_string\n        }\n      }\n      comment_count\n      content(filter: { status: \"live\" }) {\n        ... on BackgroundReading {\n          article {\n            author {\n              id\n              name\n            }\n            excerpt\n            id\n            permalink\n            title\n            published_at\n          }\n          id\n        }\n        ... on Brief {\n          created_at\n          id\n          images {\n            image_uri\n          }\n          text\n          user {\n            ... on Staff {\n              avatar_uri\n              full_description\n              id\n              league_id\n              name\n              slug\n              team_id\n            }\n          }\n        }\n        ... on Development {\n          created_at\n          id\n          text\n          tweets\n        }\n        ... on Insight {\n          created_at\n          id\n          images {\n            image_uri\n          }\n          text\n          user {\n            ... on Staff {\n              avatar_uri\n              full_description\n              id\n              league_id\n              name\n              slug\n              team_id\n            }\n          }\n        }\n        ... on RelatedArticle {\n          id\n          article {\n            author {\n              id\n              name\n            }\n            excerpt\n            id\n            image_uri\n            permalink\n            published_at\n            title\n          }\n        }\n        ... on RelatedPodcastEpisode {\n          id\n          podcast_episode {\n            description\n            duration_formatted\n            id\n            image_uri\n            permalink\n            series_title\n            title\n          }\n        }\n      }\n      custom_meta_description\n      custom_search_title\n      disable_comments\n      headline\n      headline_type\n      id\n      images {\n        image_height\n        image_uri\n        image_width\n        thumbnail_height\n        thumbnail_uri\n        thumbnail_width\n      }\n      last_activity_at\n      lede\n      localization\n      lock_comments\n      permalink\n      published_at\n      short_title\n      slug\n      smart_brevity\n      smart_brevity_cta\n      smart_brevity_headers\n      tags {\n        game {\n          id\n          league\n          title\n        }\n        leagues {\n          id\n          league\n          title\n          shortname\n          sportType\n        }\n        players {\n          id\n          league\n          title\n        }\n        teams {\n          id\n          league\n          title\n          leagueShortname\n          sportType\n        }\n      }\n    }\n  }\n",
                 "variables": {"id": paths[-1]}}
    gql_json = utils.post_url('https://theathletic.com/graphql', json_data=post_data)
    if not gql_json:
        gql_url = 'https://theathletic.com/graphql?operationName=NewsItemPage&variables=%7B%22id%22%3A%22{}%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22fe0ac1ced437471962539d24bc6e5828e125f98a5a8c502a5998a532347f775b%22%7D%7D'.format(paths[-1])
        gql_json = utils.get_url_json(gql_url)
    if gql_json:
        article_json = gql_json['data']['newsById']
        next_data = None
    else:
        next_data = get_next_data()
        if next_data:
            article_json = next_data['props']['apolloState']['News:' + paths[-1]]
        else:
            return None

    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    return get_news_item(article_json, next_data, args, site_json, save_debug)


def get_news_item(article_json, next_data, args, site_json, save_debug):
    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['permalink']
    item['title'] = article_json['headline']

    tz_est = pytz.timezone('US/Eastern')
    dt_est = datetime.fromtimestamp(article_json['published_at'] / 1000)
    dt = tz_est.localize(dt_est).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt_est = datetime.fromtimestamp(article_json['last_activity_at'] / 1000)
    dt = tz_est.localize(dt_est).astimezone(pytz.utc)
    item['date_modified'] = dt.isoformat()

    # Check age
    if 'age' in args:
        if not utils.check_age(item, args):
            return None

    if article_json.get('byline_linkable') and article_json['byline_linkable'].get('raw_string'):
        item['author'] = {"name": article_json['byline_linkable']['raw_string']}
    else:
        item['author'] = {"name": "The Athletic Staff"}

    if article_json.get('tags'):
        item['tags'] = []
        for key, val in article_json['tags'].items():
            if isinstance(val, list):
                for it in val:
                    if it.get('title'):
                        item['tags'].append(it['title'])
                    elif it.get('__ref') and next_data:
                        tag = next_data['props']['apolloState'][it['__ref']]
                        item['tags'].append(tag['title'])

    if article_json.get('custom_meta_description'):
        item['summary'] = article_json['custom_meta_description']

    item['content_html'] = ''
    if article_json.get('images'):
        item['_image'] = article_json['images'][0]['image_uri']
        item['content_html'] += utils.add_image(item['_image'])

    item['content_html'] += wp_posts.format_content(article_json['lede'], item)

    if article_json.get('smart_brevity'):
        item['content_html'] += '<hr/>' + article_json['smart_brevity']

    if len(article_json['images']) > 1:
        for image in article_json['images'][1:]:
            item['content_html'] += utils.add_image(image['image_uri'])

    item['content_html'] = item['content_html'].replace(' class="ath_autolink"', '')
    item['content_html'] = item['content_html'].replace('<span class="Apple-converted-space">\u00a0</span>', '&nbsp;')
    return item


def get_news_feed(url, args, site_json, save_debug):
    # This gets the articles and contents
    post_data = {"query": "\n  query NewsPage($limit: Int, $filter: NewsFilter) {\n    news(limit: $limit, filter: $filter) {\n      ...News_news\n    }\n  }\n\n\n  fragment News_news on News {\n    byline\n    byline_authors {\n      ... on Staff {\n        avatar_uri\n        bio\n        description\n        id\n        league_id\n        league_avatar_uri\n        name\n        role\n        slack_user_id\n        team_id\n        team_avatar_uri\n      }\n    }\n    byline_linkable {\n      ... on LinkableString {\n        raw_string\n        app_linked_string\n        web_linked_string\n      }\n    }\n    comment_count\n    created_at\n    custom_meta_description\n    custom_search_title\n    disable_comments\n    experts_group {\n      ... on Staff {\n        avatar_uri\n        bio\n        description\n        id\n        league_id\n        league_avatar_uri\n        name\n        role\n        slack_user_id\n        team_id\n        team_avatar_uri\n      }\n    }\n    has_unpublished_changes\n    headline\n    headline_type\n    id\n    images {\n      image_height\n      image_uri\n      image_width\n      thumbnail_height\n      thumbnail_uri\n      thumbnail_width\n    }\n    importance\n    last_activity_at\n    lede\n    localization\n    lock_comments\n    permalink\n    primary_tag {\n      title\n    }\n    published_at\n    slug\n    smart_brevity\n    smart_brevity_cta\n    status\n    tags {\n      game {\n        id\n        league\n        title\n      }\n      leagues {\n        id\n        league\n        title\n        shortname\n        sportType\n      }\n      players {\n        id\n        league\n        title\n      }\n      teams {\n        id\n        league\n        title\n        leagueShortname\n        sportType\n      }\n    }\n    updated_at\n    user_id\n    version\n  }\n\n",
        "variables": {"limit": 10, "filter": {"status": "live", "region": "us"}}}
    gql_json = utils.post_url('https://theathletic.com/graphql', json_data=post_data)
    if not gql_json:
        # This just gets the article urls
        post_data = {
            "query": "\n  query NewsPageMoreHeadlines($limit: Int, $region: Region) {\n    news(filter: { region: $region }, limit: $limit) {\n      headline\n      id\n      permalink\n    }\n  }\n",
            "variables": {"limit": 10, "region": "us"}}
        gql_json = utils.post_url('https://theathletic.com/graphql', json_data=post_data)
        if not gql_json:
            gql_url = 'https://theathletic.com/graphql?operationName=NewsPageMoreHeadlines&variables=%7B%22limit%22%3A10%2C%22region%22%3A%22us%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%221c09e535aed0238955e1f5fa61c919b2f9e26af58030bea1db53a16ad71281d4%22%7D%7D'
            gql_json = utils.get_url_json(gql_url)
    if not gql_json:
        return None

    n = 0
    feed_items = []
    for article in gql_json['data']['news']:
        if save_debug:
            logger.debug('getting content from ' + article['permalink'])
        if article.get('lede'):
            item = get_news_item(article, None, args, site_json, save_debug)
        else:
            item = get_news_content(article['permalink'], args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    feed['title'] = 'The Athletic | News'
    feed['items'] = feed_items.copy()
    return feed


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
    item['content_html'] = '<table><tr><td><a href="{}"><img src="{}"/></a></td><td style="vertical-align:top;"><h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small><a href="{}">{}</a><br/>{}</small></td></tr></table'.format(audio_url, poster, ep_url, item['title'], show_url, item['author']['name'], item['summary'])
    return item


def get_content(url, args, site_json, save_debug=False):
    if '/news/' in url:
        return get_news_content(url, args, site_json, save_debug)
    elif 'podcast-clip' in url:
        return get_podcast_clip(url, args, site_json, save_debug)

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    post_data = {"query": "\n  query ArticleViewQuery($id: ID!, $is_amp: Boolean = false, $is_preview: Boolean = false) {\n    articleById(id: $id, is_amp: $is_amp, is_preview: $is_preview) {\n      ...article\n    }\n  }\n\n  fragment article on Article {\n    article_body\n    article_body_desktop\n    article_body_mobile\n    authors {\n      author {\n        ... on Staff {\n          avatar_uri\n          bio\n          role\n          slug\n          twitter\n        }\n        first_name\n        name\n        id\n      }\n    }\n    byline_linkable {\n      ... on LinkableString {\n        raw_string\n        web_linked_string\n      }\n    }\n    chartbeat_authors {\n      author {\n        id\n        name\n        ... on Staff {\n          slug\n        }\n      }\n    }\n    chartbeat_sections\n    comment_count\n    disable_comments\n    entity_keywords\n    excerpt\n    featured\n    hide_upsell_text\n    id\n    image_uri\n    image_caption\n    inferred_league_ids\n    is_article_locked\n    is_teaser\n    is_premier\n    is_saved\n    is_unpublished\n    last_activity_at\n    league_ids\n    lock_comments\n    permalink\n    post_type_id\n    primary_tag\n    published_at\n    short_title\n    show_rating\n    subscriber_score\n    team_hex\n    team_ids\n    title\n    truncated_article_body\n  }\n",
                 "variables": {"id": paths[0]}}
    gql_json = utils.post_url('https://theathletic.com/graphql', json_data=post_data)
    if gql_json:
        article_json = gql_json['data']['articleById']
    else:
        next_data = get_next_data(url)
        if next_data['props']['pageProps'].get('article'):
            article_json = next_data['props']['pageProps']['article']
        else:
            logger.waring('unhandled article ' + url)
            return None

    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['permalink']
    item['title'] = article_json['title']

    tz_est = pytz.timezone('US/Eastern')
    dt_est = datetime.fromtimestamp(article_json['published_at'] / 1000)
    dt = tz_est.localize(dt_est).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt_est = datetime.fromtimestamp(article_json['last_activity_at'] / 1000)
    dt = tz_est.localize(dt_est).astimezone(pytz.utc)
    item['date_modified'] = dt.isoformat()

    # Check age
    if 'age' in args:
        if not utils.check_age(item, args):
            return None

    if article_json.get('byline_linkable') and article_json['byline_linkable'].get('raw_string'):
        item['author'] = {"name": article_json['byline_linkable']['raw_string']}
    elif article_json.get('authors'):
        authors = []
        for it in article_json['authors']:
            authors.append(it['author']['name'])
        if authors:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author'] = {"name": "The Athletic Staff"}

    item['tags'] = []
    if article_json.get('entity_keywords'):
        for tag in re.findall(r'([^,]+)(,|$)\s?', article_json['entity_keywords']):
            if tag[0] not in item['tags']:
                item['tags'].append(tag[0])
    if article_json.get('chartbeat_sections'):
        for tag in re.findall(r'([^,]+)(,|$)\s?', article_json['chartbeat_sections']):
            if tag[0] not in item['tags']:
                item['tags'].append(tag[0])
    if not item.get('tags'):
        del item['tags']

    item['summary'] = article_json['excerpt']

    item['content_html'] = ''
    if article_json.get('image_uri'):
        item['_image'] = article_json['image_uri']
        item['content_html'] += utils.add_image(item['_image'], article_json['image_caption'])

    item['content_html'] += wp_posts.format_content(article_json['article_body_desktop'], item)
    item['content_html'] = item['content_html'].replace(' class="ath_autolink"', '')
    item['content_html'] = item['content_html'].replace('<span class="Apple-converted-space">\u00a0</span>', '&nbsp;')
    return item


def get_feed(url, args, site_json, save_debug=False):
    if 'rss' in args['url']:
        return rss.get_feed(url, args, site_json, save_debug, get_content)
    if '/news/' in args['url']:
        return get_news_feed(args, site_json, save_debug)
    return None


def test_handler():
    feeds = ['https://theathletic.com/rss-feed/',
             'https://theathletic.com/author/jason-lloyd/?rss=1',
             'https://theathletic.com/tag/a1-must-read-stories/?rss=1',
             'https://theathletic.com/news/']
    for url in feeds:
        get_feed({"url": url}, True)
