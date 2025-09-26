import curl_cffi
from bs4 import BeautifulSoup
from datetime import datetime
from dateutil import tz

from urllib.parse import quote_plus, urlencode, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    post_data = {
        "query": "query Resource($url:String!) {\n    \n  enabledInstances {\n    name\n    subdomain\n    brandType\n  }\n  instance(url:$url) {\n    _id\n    name\n    theme\n    brandType\n    headerType\n    primaryColorOverride\n    secondaryColorOverride\n    darkLogoUrl\n    lightLogoUrl\n    holdingPageTitle\n    iconType\n    enabled\n    holdingPageSubtitle\n    holdingImageAlt\n    cookieConsentId\n    pianoEnabled\n    pianoApplicationId\n    pianoApiToken\n    pianoSubscriptionId\n    pianoDmpSiteGroupId\n    robotsTxt\n    images {\n      holding_landscape_1920 {\n        url\n      }\n      holding_landscape_1048 {\n        url\n      }\n      holding_portrait_400 {\n        url\n      }\n      holding_portrait_600 {\n        url\n      }\n      share_landscape_1920 {\n        url\n      }\n      share_landscape_1048 {\n        url\n      }\n    }\n    subdomain\n    strapline\n    facebookId\n    twitterId\n    linkedinId\n    youtubeId\n    instagramId\n    mediumId\n    issuPublicationId\n    editorialContactFormToEmailAddress\n    salesforceId\n    googleTagManagerId\n    headerAdvertVisible\n    preventAdsOnMobile\n    headerAdvertBelowNav\n    headerAdvertSlotName\n    advertSiteId\n    featureFlags\n    keyValueTargeting {\n      key\n      value\n    }\n    googleOptimizeContainerId\n    googleOptimizeAsynchronous\n    navItems {\n      title\n      url\n      type\n      subItems {\n        title\n        type\n        url\n      }\n    }\n    footerNavItems {\n      title\n      url\n      type\n      subItems {\n        title\n        type\n        url\n      }\n    }\n    footerNavInstanceLinks {\n      title\n      url\n    }\n  }\n  latestArticles(url:$url) {\n    headline\n    fullUrlPath\n    eventId\n    eventBaseSlug\n    eventArticleCategoryKey\n  }\n  latestMagazineIssue(url:$url) {\n    slug\n    images {\n      cover_321x446_150 {\n        url\n      }\n      cover_321x446_300 {\n        url\n      }\n    }\n  }\n  dmpSiteGroups {\n    results\n  }\n\n    resource(url:$url) {\n      __typename\n      ...on Redirect {\n        redirectUrl\n      }\n      ...on Article {\n    \n  _id\n  headline\n  sell\n  metaTitle\n  metaDescription\n  shareTitle\n  shareDescription\n  displayDate\n  advertSlotName\n  eventRegistrationLink\n  issue\n  issueSlug\n  pageNumber\n  contentType\n  subContentType\n  address\n  fullUrlPath\n  startDate\n  endDate\n  localeSafeStartTime\n  localeSafeEndTime\n  timezone\n  author {\n    name\n    slug\n  }\n  category\n  eventId\n  eventBaseSlug\n  eventArticleCategoryKey\n  subAttribution\n  companies {\n    _id\n    name\n    slug\n    description\n    shortDescription\n    images {\n      logo_free_127 {\n        url\n      }\n    }\n  }\n  partners {\n    _id\n    name\n    website\n  }\n  executives {\n    name\n    slug\n    bio\n    companyId\n    jobTitle\n    images {\n      headshot_220x347_220 {\n        url\n      }\n    }\n  }\n  price\n  downloadUrl\n  tags {\n    tag\n  }\n  signUpRequired\n  images {\n    thumbnail_landscape_322 {\n      \n  url\n  caption\n  link\n\n    }\n    thumbnail_landscape_138 {\n      \n  url\n  caption\n  link\n\n    }\n    thumbnail_landscape_206 {\n      \n  url\n  caption\n  link\n\n    }\n    thumbnail_landscape_290 {\n      \n  url\n  caption\n  link\n\n    }\n    thumbnail_landscape_330 {\n      \n  url\n  caption\n  link\n\n    }\n    thumbnail_landscape_412 {\n      \n  url\n  caption\n  link\n\n    }\n    thumbnail_landscape_580 {\n      \n  url\n  caption\n  link\n\n    }\n    thumbnail_landscape_900 {\n      \n  url\n  caption\n  link\n\n    }\n    thumbnail_portrait_144 {\n      \n  url\n  caption\n  link\n\n    }\n    thumbnail_portrait_286 {\n      \n  url\n  caption\n  link\n\n    }\n    thumbnail_portrait_576 {\n      \n  url\n  caption\n  link\n\n    }\n    thumbnail_widescreen_553 {\n      \n  url\n  caption\n  link\n\n    }\n    hero_landscape_320 {\n      \n  url\n  caption\n  link\n\n    }\n    hero_landscape_668 {\n      \n  url\n  caption\n  link\n\n    }\n    hero_landscape_900 {\n      \n  url\n  caption\n  link\n\n    }\n    hero_landscape_1336 {\n      \n  url\n  caption\n  link\n\n    }\n    hero_landscape_1800 {\n      \n  url\n  caption\n  link\n\n    }\n    hero_portrait_144 {\n      \n  url\n  caption\n  link\n\n    }\n    hero_widescreen_320 {\n      \n  url\n  caption\n  link\n\n    }\n    hero_widescreen_668 {\n      \n  url\n  caption\n  link\n\n    }\n    hero_widescreen_900 {\n      \n  url\n  caption\n  link\n\n    }\n    hero_widescreen_1336 {\n      \n  url\n  caption\n  link\n\n    }\n    hero_widescreen_1800 {\n      \n  url\n  caption\n  link\n\n    }\n    thumbnail_landscape_138 {\n      \n  url\n  caption\n  link\n\n    }\n    thumbnail_landscape_206 {\n      \n  url\n  caption\n  link\n\n    }\n    share_widescreen_1200 {\n      \n  url\n  caption\n  link\n\n    }\n  }\n  videoProvider\n  videoId\n  issuPublicationId\n  issuIssueId\n  magazineOrigin\n  slug\n  section {\n    _id\n    slug\n    advertSectionId\n    keyValueTargeting {\n      key\n      value\n    }\n    layouts {\n      article {\n        layout {\n          attributes\n          background\n          cols {\n            width\n            attributes\n            widgetArea {\n              \n  widgets {\n    \n  ... on Widget {\n    id\n    type\n    displayOptions\n    essential\n  }\n,\n  ... on ArticleLayoutHeader {\n    id\n  }\n,\n  ... on TextWidget {\n    html\n  }\n,\n  ... on BlockquoteWidget {\n    html\n    attribution\n    buttonText\n    buttonLink\n  }\n,\n... on AdvertWidget {\n  slotName\n  size\n  suffix\n  alignment\n  background\n  keyValueTargeting {\n    key\n    value\n  }\n}\n,\n  ... on ArticleLayoutTags {\n    id\n  }\n,\n  ... on ArticleGridWidget {\n    displayCategory\n    dedupe\n    limit\n    lists\n    displayType\n    articles {\n      results {\n        _id\n        headline\n        eventId\n        eventBaseSlug\n        eventArticleCategoryKey\n        fullUrlPath\n        featured\n        quote\n        category\n        contentType\n        startDate\n        timezone\n        timezoneCorrectStartDate\n        timezoneCorrectEndDate\n        localeSafeStartTime\n        localeSafeEndTime\n        address\n        tags {\n          tag\n        }\n        attribution\n        subAttribution\n        sell\n        images {\n          thumbnail_landscape_138 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_landscape_206 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_landscape_290 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_landscape_330 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_landscape_412 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_landscape_580 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_landscape_900 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_portrait_104 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_portrait_208 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_portrait_290 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_portrait_580 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_portrait_720 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_portrait_900 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_widescreen_322 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_widescreen_553 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_widescreen_644 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_widescreen_1106 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_widescreen_290 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n        }\n      }\n    }\n  }\n,\n  ... on ArticleStackWidget {\n    dedupe\n    limit\n    lists\n    articles {\n      results {\n        _id\n        headline\n        fullUrlPath\n        sell\n        images {\n          thumbnail_landscape_322 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n        }\n      }\n    }\n  }\n,\n  ... on VideoGridWidget {\n    title\n    viewAllCtaLink\n    dedupe\n    limit\n    suffix\n    slotName\n    background\n    articles {\n      results {\n        _id\n        headline\n        eventId\n        eventBaseSlug\n        eventArticleCategoryKey\n        fullUrlPath\n        sell\n        featured\n        category\n        tags {\n          tag\n        }\n        images {\n          thumbnail_widescreen_644 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n        }\n      }\n    }\n    keyValueTargeting {\n      key\n      value\n    }\n  }\n,\n  ... on CarouselWidget {\n    dedupe\n    limit\n    itemsPerRow\n    articles {\n      results {\n        _id\n        headline\n        eventId\n        eventBaseSlug\n        eventArticleCategoryKey\n        sell\n        fullUrlPath\n        contentType\n        startDate\n        address\n        images {\n          thumbnail_landscape_290 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_landscape_412 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_landscape_580 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_landscape_900 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_widescreen_322 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_widescreen_553 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_widescreen_644 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_widescreen_1106 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_landscape_138 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n          thumbnail_landscape_206 {\n            url\ncaption\nlink\nalt\nwidth\nheight\nratio\n          }\n        }\n      }\n    }\n  }\n,\n  ... on HeaderWidget {\n    title\n    viewAllCtaLink\n    large\n  }\n,\n  ... on HtmlWidget {\n    html\n  }\n,\n  ... on ArticleLayoutShare {\n    id\n  }\n,\n  ... on ArticleLayoutStoryCta {\n    id\n    magazine {\n      slug\n      images {\n        cover_321x446_150 {\n          url\n          caption\n          link\n        }\n      }\n    }\n  }\n,\n  ... on ArticleLayoutEventInfo {\n    id\n  }\n,\n  ... on ArticleLayoutDownload {\n    id\n  }\n,\n  ... on ArticleLayoutStandfirst {\n    id\n  }\n,\n  ... on ArticleLayoutImages {\n    id\n  }\n,\n  ... on ArticleLayoutRelatedContentWidget {\n    relatedContent {\n      _id\n      headline\n      eventId\n      eventBaseSlug\n      eventArticleCategoryKey\n      fullUrlPath\n      category\n    }\n  }\n,\n  ... on ArticleLayoutRelatedEntities {\n    id\n  }\n,\n  ... on ArticleLayoutEventRegistration {\n    id\n  }\n,\n  ... on ArticleLayoutImages {\n    id\n  }\n,\n  ... on PartnersWidget {\n    id\n  }\n,\n  ... on MagazineCtaWidget {\n    id\n    variation\n  }\n,\n  ... on EventLatestCTA {\n    id\n    event {\n      startDate\n      endDate\n      lightLogoUrl\n      darkLogoUrl\n      _fullUrl\n      city\n      brandColor\n      backgroundVideoId\n    }\n    backgroundURL\n    textOverride\n    videoId\n  }\n,\n  ... on MagazineLatestCTAWidget {\n    title\n    magazineIssues {\n      issueDate\n      slug\n      images {\n        cover_321x446_321 {\n          url\n        }\n        cover_321x446_642 {\n          url\n        }\n      }\n    }\n  }\n\n  }\n\n            }\n          }\n        }\n      }\n    }\n    setArticleIdAsKeyValuePair\n    articleIdKeyToSet\n  }\n  migratedFromId\n  canonicalUrl\n  \n  body {\n    \n  widgets {\n    \n  ... on Widget {\n    id\n    type\n    displayOptions\n    essential\n  }\n,\n  ... on HtmlWidget {\n    html\n  }\n,\n  ... on InlineImageWidget {\n    inlineImageImages: images {\n      crop\n      destination\n      opensInNewTab\n      images {\n        inline_landscape_668 {\n          url\ncaption\nlink\nalt\nwidth\nheight\nratio\n        }\n        inline_landscape_900 {\n          url\ncaption\nlink\nalt\nwidth\nheight\nratio\n        }\n        inline_landscape_1336 {\n          url\ncaption\nlink\nalt\nwidth\nheight\nratio\n        }\n        inline_landscape_1800 {\n          url\ncaption\nlink\nalt\nwidth\nheight\nratio\n        }\n        inline_free_668 {\n          url\ncaption\nlink\nalt\nwidth\nheight\nratio\n        }\n        inline_free_900 {\n          url\ncaption\nlink\nalt\nwidth\nheight\nratio\n        }\n        inline_free_1336 {\n          url\ncaption\nlink\nalt\nwidth\nheight\nratio\n        }\n        inline_free_1800 {\n          url\ncaption\nlink\nalt\nwidth\nheight\nratio\n        }\n      }\n    }\n  }\n,\n  ... on InlineVideoWidget {\n    provider\n    videoId,\n    videoCaption\n  }\n,\n  ... on TextWidget {\n    html\n  }\n,\n  ... on BlockquoteWidget {\n    html\n    attribution\n    buttonText\n    buttonLink\n  }\n,\n  ... on PodcastWidget {\n    spotifyPodcastEpisodeId\n  }\n,\n  ... on PaginatedListWidget {\n    itemsPerPage\n    totalItems\n    items {\n      title\n      text\n      images {\n        hero_landscape_668 {\n          url\ncaption\nlink\nalt\nwidth\nheight\nratio\n        }\n      }\n    }\n  }\n,\n  ... on KeyFactsWidget {\n    title\n    keyFacts {\n      text\n    }\n  }\n,\n  ... on TweetWidget {\n    tweetId\n    tweetContent\n  }\n\n  }\n\n  }\n\n\n  }\n    }\n  }",
        "variables": {
            "url": url
        }
    }
    r = curl_cffi.post('https://' + split_url.netloc + '/graphql', json=post_data, headers={"accept": "application/json"}, impersonate='chrome', proxies=config.proxies)
    if not r or r.status_code != 200:
        return None
    # if save_debug:
    #     utils.write_file(r.text, './debug/debug.txt')
    gql_json = r.json()
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')

    article_json = gql_json['data']['resource']
    item = {}
    item['id'] = article_json['_id']
    item['url'] = url
    item['title'] = article_json['headline']

    dt = datetime.fromisoformat(article_json['displayDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {
        "name": article_json['author']['name']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    item['tags'] = []
    if article_json.get('category'):
        item['tags'].append(article_json['category'])
    if article_json.get('tags'):
        item['tags'] += [x['tag'] for x in article_json['tags']]
    if article_json.get('companies'):
        item['tags'] += [x['name'] for x in article_json['companies'] if x['name'] not in item['tags']]
    if len(item['tags']) == 0:
        del item['tags']

    item['content_html'] = ''
    if article_json.get('sell'):
        item['summary'] = article_json['sell']
        item['content_html'] += '<p><em>' + article_json['sell'] + '</em></p>'

    if article_json.get('images'):
        item['image'] = article_json['images']['hero_widescreen_900'][0]['url']
        item['content_html'] += utils.add_image(article_json['images']['hero_widescreen_900'][0]['url'], article_json['images']['hero_widescreen_900'][0].get('caption'), link=article_json['images']['hero_widescreen_900'][0].get('link'))

    for widget in article_json['body']['widgets']:
        if widget['type'] == 'text':
            item['content_html'] += widget['html']
        elif widget['type'] == 'inlineImage':
            images = next((it for it in widget['inlineImageImages'] if it['crop'] == 'Landscape'), None)
            if images:
                image = images['images']['inline_landscape_900'][0]
            elif widget['inlineImageImages'][0]['crop'] == 'Free':
                image = widget['inlineImageImages'][0]['images']['inline_free_900'][0]
            else:
                logger.warning('unknown inlineImage crop ' + widget['inlineImageImages'][0]['crop'])
                image = widget['inlineImageImages'][0]['images']['inline_portrait_576'][0]
            item['content_html'] += utils.add_image(image['url'], image.get('caption'), link=image.get('link'))
        elif widget['type'] == 'inlineVideo' and widget['provider'] == 'youtube':
            item['content_html'] += utils.add_embed('https://www.youtube.com/watch?v=' + widget['videoId'])
        elif widget['type'] == 'keyFacts':
            item['content_html'] += '<hr style="margin:1em 0;">'
            if widget.get('title'):
                item['content_html'] += '<div style="text-transform:uppercase; color:rgb(239,61,59); font-weight:bold;">' + widget['title'] + '</div>'
            item['content_html'] += '<ul>'
            for it in widget['keyFacts']:
                item['content_html'] += '<li style="margin:1em 0; font-weight:bold;">' + it['text'] + '</li>'
            item['content_html'] += '</ul><hr style="margin:1em 0;">'
        else:
            logger.warning('unhandled body widget type {} in {}'.format(widget['type'], item['url']))

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    post_data = {
        "query": "\n  query PaginatedQuery($url:String!, $page: Int = 1, $widgetType: String!, $currentArticleIds: JSON) {\n    paginatedWidget(url: $url, widgetType: $widgetType, currentArticleIds: $currentArticleIds) {\n      ... on SimpleArticleGridWidget {\n        articles(page: $page) {\n          total\n          results {\n            _id\n            headline\n            eventId\n            eventBaseSlug\n            eventArticleCategoryKey\n            fullUrlPath\n            featured\n            quote\n            category\n            contentType\n            tags {\n              tag\n            }\n            attribution\n            subAttribution\n            sell\n            images {\n              thumbnail_landscape_322 {\n                url\n              }\n              thumbnail_portrait_286 {\n                url\n              }\n              thumbnail_widescreen_553 {\n                url\n              }\n            }\n            address\n            startDate\n          }\n        }\n      }\n    }\n  }\n",
        "variables": {
            "widgetType": "simpleArticleGrid",
            "page": 0,
            "url": url,
            "currentArticleIds":{}
        }
    }
    r = curl_cffi.post('https://' + split_url.netloc + '/graphql', json=post_data, headers={"accept": "application/json"}, impersonate='chrome', proxies=config.proxies)
    if not r or r.status_code != 200:
        return None
    # if save_debug:
    #     utils.write_file(r.text, './debug/debug.txt')    
    gql_json = r.json()
    if save_debug:
        utils.write_file(gql_json, './debug/feed.json')

    n = 0
    feed_items = []
    for article in gql_json['data']['paginatedWidget']['articles']['results']:
        article_url = 'https://' + split_url.netloc + article['fullUrlPath']
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_content(article_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    # feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed