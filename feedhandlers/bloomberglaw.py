import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import utils
from feedhandlers import bloomberg, rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    data = [
        {
            "operationName": "getArticle",
            "variables": {
                "channelUrl": paths[0],
                "url": paths[1]
            }
        }
    ]
    data[0]['query'] = '''
query getArticle($channelUrl: String!, $url: String!) {
  article: articleByUrl(channelUrl: $channelUrl, url: $url) {
    ...ArticleContent
    free
    body
    bodyJson
    noIndex
    terminalSuid
    __typename
  }
}

fragment ArticleContent on Article {
  __typename
  id
  headline
  subHeadline
  type
  authorized
  postedDate
  updatedDate
  byline
  snapshot
  url
  contactUs
  revisionNumber
  canonicalUrl
  blpCanonicalUrl
  summary
  guestSpeaker
  storyTag
  storyPresentationStyle
  socialMediaPost
  terminalSuids
  ledeGraphic {
    __typename
    id
    externalId
    provider {
      __typename
      displayName
    }
  }
  imageLede {
    __typename
    id
    ARTICLE_LEDE: url(dimensions: ARTICLE_LEDE)
    alternateText
    caption
    credit
  }
  currentRevision {
    __typename
    id
    note
    date
  }
  reporters {
    __typename
    id
    name
    attributedRole
    position
    email
    twitter
    avatar {
      __typename
      imageUrl(dimensions: AUTHOR_IMAGE)
    }
    reporter {
      authorProfile {
        blpBioId
        __typename
      }
      __typename
    }
  }
  contributors {
    __typename
    id
    name
    position
    email
    avatar {
      __typename
      imageUrl(dimensions: AUTHOR_IMAGE)
    }
    contributor {
      __typename
      id
      contributorType
      authorProfile {
        blpBioId
        __typename
      }
    }
  }
  relatedArticles {
    __typename
    id
    headline
    postedDate
    url
    channel {
      __typename
      id
      url
    }
  }
  relatedDocuments {
    __typename
    ... on ExternalLink {
      id
      __typename
      text
      target
      url
      documentType
    }
  }
  topics {
    __typename
    id
    name
  }
  companies {
    __typename
    id
    name
  }
  lawFirms {
    __typename
    id
    name
  }
  channel {
    __typename
    id
    name
    url
    productCode
    brand {
      id
      name
      __typename
    }
  }
  channels {
    __typename
    id
    brand {
      id
      name
      brandCode
      __typename
    }
    derivedChannels {
      __typename
      id
      productCode
      brand {
        brandCode
        __typename
      }
    }
  }
}
'''
    gql_json = utils.post_url('https://bwrite-api.bna.com/graphql', json_data=data)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')

    article_json = gql_json[0]['data']['article']
    if article_json['authorized'] == False:
        search_json = bloomberg.get_bb_url('https://www.bloomberg.com/nemo-next/api/search/query?query=' + quote_plus(article_json['headline']), get_json=True)
        if search_json:
            title = re.sub(r'\W', '', article_json['headline']).lower()
            for it in search_json['results']:
                if re.sub(r'\W', '', it['headline']).lower() in title:
                    return bloomberg.get_content(it['url'], args, site_json, save_debug)

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['canonicalUrl']
    item['title'] = article_json['headline']

    dt = datetime.fromisoformat(article_json['postedDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if article_json.get('reporters'):
        item['authors'] = [{"name": x['name']} for x in article_json['reporters']]
    elif article_json.get('contributors'):
        item['authors'] = [{"name": x['name']} for x in article_json['contributors']]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = []
    if article_json.get('channel'):
        item['tags'].append(article_json['channel']['name'])
    if article_json.get('topics'):
        item['tags'] += [x['name'] for x in article_json['topics']]
    if article_json.get('companies'):
        item['tags'] += [x['name'] for x in article_json['companies']]
    if article_json.get('lawFirms'):
        item['tags'] += [x['name'] for x in article_json['lawFirms']]

    if article_json.get('summary'):
        item['summary'] = BeautifulSoup(article_json['summary'], 'html.parser').get_text(strip=True)

    item['content_html'] = ''
    if article_json.get('subHeadline'):
        item['content_html'] += '<p><em>' + article_json['subHeadline'] + '</em></p>'
    if article_json.get('snapshot'):
        item['content_html'] += article_json['snapshot']

    if article_json.get('imageLede'):
        if 'url' in article_json['imageLede']:
            item['image'] = article_json['imageLede']['url']
        elif 'ARTICLE_LEDE' in article_json['imageLede']:
            item['image'] = article_json['imageLede']['ARTICLE_LEDE']
        if 'image' in item:
            captions = []
            if article_json['imageLede'].get('caption'):
                captions.append(article_json['imageLede']['caption'])
            if article_json['imageLede'].get('credit'):
                captions.append(article_json['imageLede']['credit'])
            item['content_html'] += utils.add_image(item['image'], ' | '.join(captions))
        else:
            logger.warning('unhandled imageLede in ' + item['url'])

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    soup = BeautifulSoup(article_json['body'], 'html.parser')
    if soup.contents[0].name == 'div':
        soup.contents[0].unwrap()
    for el in soup.find_all('bw-company'):
        el.unwrap()

    for el in soup.find_all(class_='embedded-image'):
        img = el.find('img')
        if img:
            captions = []
            it = el.find(class_='label')
            if it:
                captions.append(it.get_text().strip())
            it = el.find(class_='attribution')
            if it:
                captions.append(it.get_text().strip())
            new_html = utils.add_image(img['src'], ' | '.join(captions))
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

    item['content_html'] += str(soup)

    if article_json.get('currentRevision'):
        item['content_html'] += '<p><small>(' + article_json['currentRevision']['note'] + ')</small></p>'

    if article_json['authorized'] == False:
        item['content_html'] += '<h3 style="text-align:center; color:red;">A subscription is required for the full content</h3>'

    if article_json.get('relatedDocuments'):
        item['content_html'] += '<hr/><h3>Documents</h3><ul>'
        for it in article_json['relatedDocuments']:
            item['content_html'] += '<li><a href="{}">{}</a></li>'.format(it['url'], it['text'])
        item['content_html'] += '</ul>'

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if split_url.path.startswith('/rss/'):
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    paths = list(filter(None, split_url.path[1:].split('/')))
    feed_title = 'Bloomberg Law News'
    articles = []
    if len(paths) == 0:
        data = [
            {
                "operationName": "getFreeArticles",
                "variables": {},
                "query": "query getFreeArticles($channelIds: [String], $excludeArticleIds: [String], $startDate: String) {\n  latestFreeArticles: articles(channelIds: $channelIds, limit: 5, free: true, excludeArticleIds: $excludeArticleIds, startDate: $startDate) {\n    ...ArticleSummary\n    __typename\n  }\n}\n\nfragment ArticleSummary on ArticlesResult {\n  items {\n    id\n    headline\n    summary\n    url\n    imageLede {\n      id\n      url(dimensions: PROMO_SMALL)\n      alternateText\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n"
            },
            {
                "operationName": "getPaidArticles",
                "variables": {},
                "query": "query getPaidArticles($channelIds: [String], $excludeArticleIds: [String], $startDate: String) {\n  latestPaidArticles: articles(channelIds: $channelIds, limit: 5, free: false, excludeArticleIds: $excludeArticleIds, startDate: $startDate) {\n    ...ArticleSummary\n    __typename\n  }\n}\n\nfragment ArticleSummary on ArticlesResult {\n  items {\n    id\n    headline\n    summary\n    url\n    imageLede {\n      id\n      url(dimensions: PROMO_SMALL)\n      alternateText\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n"
            }
        ]
        gql_json = utils.post_url('https://bwrite-api.bna.com/graphql', json_data=data)
        if not gql_json:
            return None
        if save_debug:
            utils.write_file(gql_json, './debug/feed.json')
        for it in gql_json[0]['data']['latestFreeArticles']['items']:
            articles.append(it)
        for it in gql_json[1]['data']['latestPaidArticles']['items']:
            articles.append(it)
    elif len(paths) == 1:
        feed_title += ' | ' + paths[0].replace('-', ' ').title()
        data = [
            {
                "operationName": "getLanding",
                "variables": {
                    "url": paths[0]
                },
                "query": "query getLanding($url: String!) {\n  landing: channelByUrl(url: $url) {\n    id\n    name\n    url\n    shortName\n    subscribed\n    channelType\n    productCode\n    brand {\n      id\n      twitterAccount\n      brandCode\n      name\n      brandedURL\n      __typename\n    }\n    footerLinks {\n      id\n      text\n      url\n      __typename\n    }\n    landingPage {\n      socialMediaThumbnail {\n        url\n        __typename\n      }\n      socialMediaDescription\n      ...LandingPageContent\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment LandingPageContent on LandingPage {\n  id\n  pageComponents {\n    __typename\n    ...FeaturedLinksContent\n    ...LandingPageHeroesContent\n    ...TopStoriesContent\n    ...LatestStoriesContent\n    ...SideBarLinkContent\n    ...PractitionerInsightsContent\n    ...MultimediaListContent\n    ...InBriefContent\n    ...FeaturedFacetsContent\n    ...FeaturedChannelsContent\n    ...FeaturedInteractiveGraphicsContent\n    ...InteractiveStoryBannerContent\n    ...InteractiveStoriesContent\n    ...BannerLinkContent\n  }\n  __typename\n}\n\nfragment FeaturedLinksContent on FeaturedLinks {\n  title\n  links {\n    id\n    text\n    url\n    target\n    __typename\n  }\n  __typename\n}\n\nfragment LandingPageHeroesContent on LandingPageHeroes {\n  heroArticles: content(limit: 2) {\n    items {\n      headline\n      imageLede {\n        id\n        url(dimensions: PROMO_LARGE)\n        alternateText\n        __typename\n      }\n      article {\n        id\n        headline\n        url\n        imageLede {\n          id\n          url(dimensions: PROMO_LARGE)\n          alternateText\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment TopStoriesContent on TopStories {\n  title\n  displayStyle\n  displayLedeImage\n  topStoryArticles: content {\n    items {\n      headline\n      imageLede {\n        id\n        url(dimensions: MOBILE_PROMO_LARGE)\n        alternateText\n        __typename\n      }\n      article {\n        id\n        summary\n        url\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment LatestStoriesContent on LatestStories {\n  title\n  numberOfArticles\n  latestStoryArticles: articles {\n    items {\n      id\n      headline\n      summary\n      url\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment SideBarLinkContent on SideBarLinkComponent {\n  title\n  image {\n    id\n    url\n    alternateText\n    __typename\n  }\n  url\n  __typename\n}\n\nfragment PractitionerInsightsContent on PractitionerInsights {\n  insightArticles: content {\n    items {\n      headline\n      article {\n        id\n        headline\n        contributors {\n          id\n          name\n          position\n          email\n          avatar {\n            imageUrl(dimensions: AUTHOR_IMAGE)\n            __typename\n          }\n          __typename\n        }\n        url\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment MultimediaListContent on MultimediaList {\n  videos {\n    items {\n      id\n      title\n      image {\n        id\n        url(dimensions: MOBILE_PROMO_LARGE)\n        alternateText\n        __typename\n      }\n      externalId\n      description\n      url\n      provider {\n        displayName\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  podcastEpisodes {\n    items {\n      id\n      title\n      image {\n        id\n        url(dimensions: MOBILE_PROMO_LARGE)\n        alternateText\n        __typename\n      }\n      externalId\n      url\n      provider {\n        displayName\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment InBriefContent on InBrief {\n  title\n  articleTypes\n  inBriefArticles: content {\n    items {\n      headline\n      article {\n        id\n        type\n        headline\n        summary\n        url\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment FeaturedFacetsContent on FeaturedFacets {\n  title\n  findMoreLinkText\n  primaryFacets {\n    facet {\n      __typename\n      id\n      name\n    }\n    featuredFacetArticles: articles(limit: 3) {\n      items {\n        id\n        headline\n        url\n        imageLede {\n          id\n          url(dimensions: MOBILE_PROMO_LARGE)\n          alternateText\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  subHead\n  otherFacets {\n    __typename\n    id\n    name\n  }\n  __typename\n}\n\nfragment FeaturedChannelsContent on FeaturedChannels {\n  title\n  displayLedeImage\n  channel {\n    id\n    url\n    __typename\n  }\n  featuredChannelArticles: content(limit: 3) {\n    items {\n      headline\n      article {\n        id\n        headline\n        url\n        imageLede {\n          id\n          url(dimensions: MOBILE_PROMO_LARGE)\n          alternateText\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment FeaturedInteractiveGraphicsContent on FeaturedInteractiveGraphics {\n  items {\n    embedCode\n    __typename\n  }\n  __typename\n}\n\nfragment InteractiveStoryBannerContent on InteractiveStoryComponent {\n  interactiveStory {\n    id\n    slug\n    thumbnail {\n      alternateText\n      url\n      __typename\n    }\n    mobileThumbnail {\n      url\n      __typename\n    }\n    largePhoneThumbnail {\n      url\n      __typename\n    }\n    tabletThumbnail {\n      url\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment InteractiveStoriesContent on InteractiveStories {\n  interactiveStories {\n    slug\n    thumbnail {\n      alternateText\n      url\n      __typename\n    }\n    mobileThumbnail {\n      url\n      __typename\n    }\n    tabletThumbnail {\n      url\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment BannerLinkContent on BannerLinkComponent {\n  title\n  url\n  image {\n    url\n    alternateText\n    __typename\n  }\n  __typename\n}\n"
            }
        ]
        gql_json = utils.post_url('https://bwrite-api.bna.com/graphql', json_data=data)
        if not gql_json:
            return None
        if save_debug:
            utils.write_file(gql_json, './debug/feed.json')
        for comp in gql_json[0]['data']['landing']['landingPage']['pageComponents']:
            if comp['__typename'] == 'LatestStories':
                for it in comp['latestStoryArticles']['items']:
                    articles.append(it)

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