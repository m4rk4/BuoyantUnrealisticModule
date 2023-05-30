import pytz, re
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_gql_data(post_data):
    # x-api-key:
    # https://www.pgatour.com/_next/static/chunks/pages/_app-5c839b5111fd21cc.js
    # {"comment":"production env, used by live site, prod staging site","apiKey":"da2-gsrx5bibzbb4njvhl7t37wqyl4","queryEndpoint":"https://orchestrator.pgatour.com/graphql"...
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "pragma": "no-cache",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"113\", \"Chromium\";v=\"113\", \"Not-A.Brand\";v=\"24\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "x-amz-user-agent": "aws-amplify/3.0.7",
        "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
        "x-pgat-platform": "web"
    }
    return utils.post_url('https://orchestrator.pgatour.com/graphql', json_data=post_data, headers=headers)


def add_expert_picks(path):
    post_data = {
        "operationName": "GetExpertPicksTable",
        "variables":{
            "path": path
        },
        "query":"query GetExpertPicksTable($path: String!) {\n  getExpertPicksTable(path: $path) {\n    tournamentName\n    expertPicksTableRows {\n      expertName\n      expertTitle\n      lineup {\n        id\n        firstName\n        lastName\n        countryFlag\n        countryName\n        headshot\n      }\n      winner {\n        id\n        firstName\n        lastName\n        countryFlag\n        countryName\n        headshot\n      }\n      comment {\n        ...ExpertPicksComment\n      }\n    }\n  }\n}\n\nfragment ExpertPicksComment on TourSponsorDescription {\n  ... on NewsArticleParagraph {\n    __typename\n    segments {\n      type\n      value\n      data\n      format {\n        variants\n      }\n      imageOrientation\n    }\n  }\n  ... on NewsArticleText {\n    __typename\n    value\n  }\n  ... on NewsArticleLink {\n    __typename\n    segments {\n      type\n      value\n      data\n      format {\n        variants\n      }\n      imageOrientation\n    }\n  }\n  ... on NewsArticleLineBreak {\n    __typename\n    breakValue\n  }\n  ... on NewsArticleImage {\n    __typename\n    segments {\n      type\n      value\n      data\n      format {\n        variants\n      }\n      imageOrientation\n    }\n  }\n}"
    }
    gql_json = get_gql_data(post_data)
    if not gql_json:
        return ''
    utils.write_file(gql_json, './debug/picks.json')
    picks_html = '<h3>Expert Picks</h3><table style="width:100%; border-collapse:collapse;"><tr style="border-bottom:2px solid black;"><th style="text-align:left;">Winner</th><th style="text-align:left;">Players</th><th style="text-align:left;">Expert</th><th style="text-align:left;">Comment</th></tr>'
    for row in gql_json['data']['getExpertPicksTable']['expertPicksTableRows']:
        headshot = '{}/image?url={}&width=64&mask=ellipse'.format(config.server, quote_plus(row['winner']['headshot']))
        picks_html += '<tr style="border-bottom:1px solid black;"><td style="width:25%; vertical-align:top;"><img src="{}" style="float:left;"/><span style="font-size:1.1em; font-weight:bold;">{} {}</span><br/><small>{}</small></td>'.format(headshot, row['winner']['firstName'], row['winner']['lastName'], row['winner']['countryName'])
        picks_html += '<td style="width:25%; vertical-align:top;"><small>Lineup:'
        for i, player in enumerate(row['lineup']):
            if i < 4:
                picks_html += '<br/>&bull; {} {}'.format(player['firstName'], player['lastName'])
            elif i == 4:
                picks_html += '<br/>Bench:<br/>&bull; {} {}'.format(player['firstName'], player['lastName'])
            else:
                picks_html += '<br/>&bull; {} {}'.format(player['firstName'], player['lastName'])
        picks_html += '</small></td><td style="width:25%; vertical-align:top;"><span style="font-size:1.2em; font-weight:bold;">{}</span><br/><small>{}</small></td>'.format(row['expertName'], row['expertTitle'])
        comment = ''
        for node in row['comment']:
            comment += format_node(node)
        comment = re.sub(r'^<p>(.*)</p>$', r'\1', comment.replace('</p><p>', '<br/><br/>'))
        picks_html += '<td style="width:25%; vertical-align:top;">{}</td></tr>'.format(comment)
    picks_html += '</table>'
    return picks_html


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if split_url.netloc == 'res.cloudinary.com':
        # https://res.cloudinary.com/pgatour-prod/pgatour/news/editorial/2023/05/18/oak-hill-frost.jpg
        # https://res.cloudinary.com/pgatour-prod/w_1200,h_628,c_fill,f_auto/pgatour/news/editorial/2023/05/18/oak-hill-frost.jpg
        if re.search(r'w_\d+|h_\d+|c_fill|f_auto', paths[1]):
            del paths[1]
        return '{}://{}/{}/w_{},h_628,c_fill,f_auto/{}'.format(split_url.scheme, split_url.netloc, paths[0], width, '/'.join(paths[1:]))
    return img_src


def format_segment(segment):
    segment_html = ''
    if segment['type'] == 'text':
        segment_html += segment['value']
    elif segment['type'] == 'link':
        segment_html += '<a href="{}">{}</a>'.format(segment['data'], segment['value'])
    elif segment['type'] == 'line-break':
        segment_html += '<br/>'
    else:
        logger.warning('unhandled segment type ' + segment['type'])
    if segment.get('format'):
        for variant in segment['format']['variants']:
            if variant == 'bold':
                segment_html = '<b>{}</b>'.format(segment_html)
            elif variant == 'italic':
                segment_html = '<i>{}</i>'.format(segment_html)
            elif variant == 'underline':
                segment_html = '<u>{}</u>'.format(segment_html)
            else:
                logger.warning('unhandled segment format variant ' + variant)
    return segment_html


def format_node(node):
    node_html = ''
    if node['__typename'] == 'NewsArticleParagraph':
        node_html += '<p>'
        for segment in node['segments']:
            node_html += format_segment(segment)
        node_html += '</p>'
    elif node['__typename'] == 'NewsArticleHeader':
        node_html += '<{}>'.format(node['style'])
        for segment in node['headerSegments']:
            for seg in segment['segments']:
                node_html += format_segment(seg)
        node_html += '</{}>'.format(node['style'])
    elif node['__typename'] == 'NewsArticleImage':
        node_html += utils.add_image(resize_image(node['segments'][0]['data']), node['segments'][0].get('value'))
    elif node['__typename'] == 'NewsArticlePhotoGallery':
        for image in node['images']:
            node_html += format_node(image)
    elif node['__typename'] == 'NewsArticleVideo':
        video_args = {
            "data-video-id": node['video']['id'],
            "data-account": 6082840763001,
            "data-key": "BCpkADawqM0vwoTnlGSUgP84xuQaUJJUF2Hp1MT2MbyDvrD8DfnRNr57b3W-SnGPIUswIm1LLqO6pEdQf6lVX8bADNuaxAT-Lodzt2GSUUZRoUQMsUfgTuy1NYQxkKwXKRfSmCdrRF-dmXGa"
        }
        video_url = 'https://edge.api.brightcove.com/playback/v1/accounts/{}/videos/{}'.format(
            video_args['data-account'], video_args['data-video-id'])
        node_html += utils.add_embed(video_url, video_args)
    elif node['__typename'] == 'TableFragment':
        node_html += '<table style="width:100%; border-collapse:collapse;">'
        for i, row in enumerate(node['table']['rows']):
            node_html += '<tr style="border-bottom:1px solid black;">'
            for col in row['columns']:
                if i == 0:
                    tag = 'th'
                else:
                    tag = 'td'
                node_html += '<{} style="text-align:center;">'.format(tag)
                for val in col['value']:
                    node_html += format_segment(val)
                node_html += '</{}>'.format(tag)
            node_html += '</tr>'
        node_html += '</table>'
    elif node['__typename'] == 'NewsArticleBlockQuote':
        node_html += utils.add_pullquote(node['quote'], node['playerName'])
    elif node['__typename'] == 'ExpertPicksNode':
        node_html += add_expert_picks(node['path'])
    elif node['__typename'] == 'NewsArticleLineBreak':
        node_html += '<div><br/></div>'
    elif node['__typename'] == 'NewsArticleDivider':
        node_html += '<div><hr/></div>'
    else:
        logger.warning('unhandled node type ' + node['__typename'])
    return node_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    post_data = {
        "operationName": "ArticleDetails",
        "variables": {
            "path": "/content/dam/pga-tour/fragments/tours/pga-tour/{}".format('/'.join(paths[1:]))
        },
        "query": "query ArticleDetails($path: String!) {\n  articleDetails(path: $path) {\n    authorReference {\n      byLine\n      firstName\n      lastName\n      twitter\n      headshot\n    }\n    disableAds\n    datePublished\n    franchise\n    franchiseDisplayName\n    headline\n    hero {\n      image\n      video {\n        category\n        categoryDisplayName\n        created\n        description\n        duration\n        franchise\n        franchiseDisplayName\n        holeNumber\n        id\n        playerVideos {\n          firstName\n          id\n          lastName\n          shortName\n        }\n        poster\n        pubdate\n        roundNumber\n        shareUrl\n        shotNumber\n        startsAt\n        thumbnail\n        title\n        tournamentId\n        tourCode\n        year\n      }\n    }\n    metadata {\n      metadata {\n        name\n        value\n      }\n    }\n    path\n    readTime\n    relatedFacts\n    sponsor {\n      description\n      logo\n      name\n      websiteUrl\n      gam\n    }\n    brandedContent\n    url\n    moreNewsTitle\n    cta {\n      link\n      text\n    }\n    articleSponsor\n    nodes {\n      ...ArticleNode\n    }\n    overviewNodes {\n      ...ArticleNode\n    }\n    teaserAsset\n    canonicalUrl\n    shareURL\n  }\n}\n\nfragment ArticleNode on NewsArticleNode {\n  ... on NewsArticleHeader {\n    __typename\n    style\n    headerSegments {\n      class\n      headerType\n      segments {\n        data\n        format {\n          variants\n        }\n        type\n        value\n      }\n    }\n  }\n  ... on NewsArticleLineBreak {\n    ...ArticleLineBreakFields\n  }\n  ... on NewsArticleParagraph {\n    ...ArticleParagraphFields\n  }\n  ... on NewsArticleText {\n    ...ArticleTextFields\n  }\n  ... on NewsArticleVideo {\n    __typename\n    video {\n      category\n      categoryDisplayName\n      created\n      description\n      duration\n      franchise\n      franchiseDisplayName\n      holeNumber\n      id\n      playerVideos {\n        firstName\n        id\n        lastName\n        shortName\n      }\n      poster\n      pubdate\n      roundNumber\n      shareUrl\n      shotNumber\n      startsAt\n      thumbnail\n      title\n      tourCode\n      tournamentId\n      year\n    }\n    video {\n      id\n    }\n  }\n  ... on NewsArticleImage {\n    ...ArticleImageFields\n  }\n  ... on NewsArticleLink {\n    ...ArticleLinkFields\n  }\n  ... on NewsArticleDivider {\n    __typename\n    value\n  }\n  ... on NewsArticlePhotoGallery {\n    __typename\n    images {\n      ...ArticleImageFields\n    }\n  }\n  ... on NewsArticleStats {\n    __typename\n    statType\n    playerId\n    playerName\n    season\n    statId\n    statName\n    tournamentId\n  }\n  ... on NewsArticleScoreCard {\n    __typename\n    class\n    playerId\n    playerName\n    round\n    season\n    tournamentId\n  }\n  ... on NewsArticleEmbedded {\n    __typename\n    height\n    frameborder\n    scroll\n    class\n    url\n  }\n  ... on NewsArticleTweetNode {\n    __typename\n    tweetId\n  }\n  ... on NewsArticleBlockQuote {\n    __typename\n    playerId\n    playerName\n    quote\n    class\n  }\n  ... on TableFragment {\n    __typename\n    table {\n      rows {\n        ... on TableHeaderRow {\n          __typename\n          columns {\n            value {\n              type\n              value\n              data\n              format {\n                variants\n              }\n            }\n            class\n            width\n            height\n            colspan\n          }\n          class\n        }\n        ... on TableDataRow {\n          __typename\n          columns {\n            value {\n              type\n              value\n              data\n              format {\n                variants\n              }\n            }\n            class\n            width\n            height\n            colspan\n          }\n          class\n        }\n      }\n    }\n    border\n    cellpadding\n    width\n    cellspacing\n    class\n    id\n  }\n  ... on ExpertPicksNode {\n    __typename\n    path\n    isPowerRankings\n  }\n  ... on NewsArticleOddsParagraph {\n    content {\n      ... on NewsArticleText {\n        value\n      }\n      ... on NewsArticleInlineOdds {\n        marketId\n        playerId\n        tournamentId\n      }\n    }\n  }\n}\n\nfragment ArticleLineBreakFields on NewsArticleLineBreak {\n  __typename\n  breakValue\n}\n\nfragment ArticleParagraphFields on NewsArticleParagraph {\n  __typename\n  segments {\n    data\n    format {\n      variants\n    }\n    type\n    value\n  }\n}\n\nfragment ArticleTextFields on NewsArticleText {\n  __typename\n  value\n}\n\nfragment ArticleImageFields on NewsArticleImage {\n  __typename\n  segments {\n    data\n    format {\n      variants\n    }\n    type\n    value\n    imageDescription\n    imageOrientation\n  }\n}\n\nfragment ArticleLinkFields on NewsArticleLink {\n  __typename\n  segments {\n    data\n    format {\n      variants\n    }\n    type\n    value\n  }\n}"
    }
    gql_json = get_gql_data(post_data)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')
    article_json = gql_json['data']['articleDetails']

    item = {}
    item['id'] = article_json['path']
    item['url'] = article_json['url']
    item['title'] = article_json['headline']

    tz_loc = pytz.timezone('US/Eastern')
    dt_loc = datetime.fromtimestamp(article_json['datePublished']/1000)
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {}
    item['author']['name'] = '{} {}'.format(article_json['authorReference']['firstName'], article_json['authorReference']['lastName']).strip()

    item['content_html'] = ''
    if article_json['hero'].get('image'):
        item['_image'] = resize_image(article_json['hero']['image'])
        item['content_html'] += utils.add_image(item['_image'])

    for node in article_json['nodes']:
        item['content_html'] += format_node(node)

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table|/li)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if paths[0] != 'news':
        logger.warning('unhandled feed url ' + url)
        return None

    post_data = {
        "operationName": "NewsArticles",
        "variables": {
            "tour": "R",
            "limit": 10
        },
        "query": "query NewsArticles($tour: TourCode, $franchise: String, $franchises: [String!], $playerId: ID, $limit: Int, $offset: Int, $tags: [String!]) {\n  newsArticles(\n    tour: $tour\n    franchise: $franchise\n    franchises: $franchises\n    playerId: $playerId\n    limit: $limit\n    offset: $offset\n    tags: $tags\n  ) {\n    articles {\n      ...NewsArticleFragment\n    }\n    franchiseSponsors {\n      franchise\n      image\n      label\n      accessibilityText\n      backgroundColor\n    }\n  }\n}\n\nfragment NewsArticleFragment on NewsArticle {\n  id\n  headline\n  teaserHeadline\n  teaserContent\n  articleImage\n  url\n  publishDate\n  updateDate\n  franchise\n  franchiseDisplayName\n  shareURL\n  sponsor {\n    name\n    description\n    logo\n    image\n    websiteUrl\n    gam\n  }\n  brightcoveId\n  externalLinkOverride\n}"
    }
    if len(paths) > 1:
        post_data['variables']['franchise'] = paths[1]
        feed_title = paths[1].replace('-', ' ').title() + ' News | PGA TOUR'
    else:
        feed_title = 'News | PGA TOUR'
    gql_json = get_gql_data(post_data)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/feed.json')

    n = 0
    feed_items = []
    for article in gql_json['data']['newsArticles']['articles']:
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
