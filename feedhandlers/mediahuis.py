import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    gql_query = {
        "operationName": "webv2_Article_{}_full".format(site_json['brand']),
        "variables": {
            "articleId": paths[-1].replace('.html', ''),
            "brand": site_json['brand'],
            "sourcesetCroppingInput": {
                "resizeMode": "CENTER_CROP",
                "cropsMode": "LANDSCAPE",
                "fallbackResizeMode": "SMART_CROP",
                "sizes": [
                    {
                        "width": 120,
                        "height": 80,
                        "key": "xsmall"
                    },
                    {
                        "width": 160,
                        "height": 107,
                        "key": "small"
                    },
                    {
                        "width": 320,
                        "height": 213,
                        "key": "medium"
                    },
                    {
                        "width": 640,
                        "height": 427,
                        "key": "large"
                    },
                    {
                        "width": 960,
                        "height": 640,
                        "key": "xlarge"
                    },
                    {
                        "width": 1280,
                        "height": 853,
                        "key": "xxlarge"
                    }
                ]
            },
            "inlineSourcesetCroppingInput": {
                "resizeMode": "FIT_IN",
                "cropsMode": "FREE",
                "fallbackResizeMode": "FIT_IN",
                "sizes": [
                    {
                        "width": 120,
                        "height": 80,
                        "key": "xsmall"
                    },
                    {
                        "width": 160,
                        "height": 107,
                        "key": "small"
                    },
                    {
                        "width": 320,
                        "height": 213,
                        "key": "medium"
                    },
                    {
                        "width": 640,
                        "height": 427,
                        "key": "large"
                    },
                    {
                        "width": 960,
                        "height": 640,
                        "key": "xlarge"
                    },
                    {
                        "width": 1280,
                        "height": 853,
                        "key": "xxlarge"
                    }
                ]
            },
            "isPreview": False
        },
        "query": '''
      fragment relatedArticle on Article {
        title
        intro
        body(sourcesetCroppingInput: $inlineSourcesetCroppingInput)
        videos
        relativeUrl
        images {
          id
          caption
          credit
          url
          sourceSets(sourcesetCroppingInput: $sourcesetCroppingInput) {
            height
            key
            url
            width
          }
          metadata {
            cropping {
              height
              width
            }
          }
        }
      }
      
      fragment basicArticle on Article {
        body(insertDynamicAds: true sourcesetCroppingInput: $inlineSourcesetCroppingInput)
        images {
          id
          caption
          credit
          url
          sourceSets(sourcesetCroppingInput: $sourcesetCroppingInput) {
            height
            key
            url
            width
          }
          metadata {
            cropping {
              height
              width
            }
          }
        }
        infoblocks {
          content(sourcesetCroppingInput: $inlineSourcesetCroppingInput)
          title
          type
        }
        intro
        premium
        source
        subtitle
        titleSummary
        sublabel
        label
        title
        url
        relativeUrl
        webcmsId
      }

      fragment fullArticle on Article {
        ...basicArticle
        attachments {
          filename
          id
          url
        }
        author
        authors {
          name
          function
          picture {
            smartCrop(height: 96, width: 96){
              url
            }
          }
        }
        dna {
         taxonomy {
           key
           values
         }
         readingTime
        }
        externalWidgets
        publishedAt
        relatedArticles {
          ...relatedArticle
        }
        type
        tags {
          authors
          categories
          city
          dateline
        }
        videos
        audio: media {
          brand
          id
          duration
          caption
          credit
          autoplay
          type
          playerConfig {
            videoId,
            brand,
            theme,
            noAds
          }
        }
      }

      query webv2_Article_brand_full($articleId: ID!, $brand: String!, $isPreview: Boolean!, 
        $sourcesetCroppingInput: SourcesetCroppingInput, $inlineSourcesetCroppingInput: SourcesetCroppingInput) {
        article: articleById(brand: $brand, webcmsId: $articleId) @skip(if: $isPreview) {
          ...fullArticle
        }
        previewArticle: articleById(brand: $brand, uuid: $articleId, preview: $isPreview) @include(if: $isPreview) {
          ...fullArticle
        }
      }
    '''.replace('webv2_Article_brand_full', 'webv2_Article_{}_full'.format(site_json['brand']))
    }
    gql_query = utils.post_url('{}://{}/graphql-blue-mhie'.format(split_url.scheme, split_url.netloc), json_data=gql_query)
    if not gql_query:
        return None
    if save_debug:
        utils.write_file(gql_query, './debug/debug.json')

    article_json = gql_query['data']['article']
    item = {}
    item['id'] = article_json['webcmsId']
    item['url'] = article_json['url']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['publishedAt'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if article_json.get('author'):
        item['author'] = {"name": article_json['author']}
    elif article_json.get('authors'):
        logger.warning('unhandled authors in ' + item['url'])

    item['content_html'] = ''

    if article_json.get('titleSummary'):
        item['summary'] = article_json['titleSummary']
        item['content_html'] = '<p><em>' + article_json['titleSummary'] + '</em></p>'

    lede = False
    if article_json.get('videos'):
        video_json = utils.get_url_json('https://content.mediahuisvideo.be/playlist/item={}/playlist.json'.format(article_json['videos'][0]['streamone']['id']))
        if video_json:
            utils.write_file(video_json, './debug/video.json')
            video = video_json['items'][0]
            source = None
            if video['locations'].get('adaptive'):
                source = next((it for it in video['locations']['adaptive'] if it['type'].lower() == 'application/x-mpegurl'), None)
            if not source and video['locations'].get('progressive'):
                source = next((it for it in video['locations']['progressive'] if it['label'] == '720p'), None)
                if not source:
                    source = video['locations']['progressive'][0]
                source = source['sources'][0]
            lede = True
            item['content_html'] += utils.add_video(source['src'], source['type'], video['poster'], video.get('title'))
            item['_image'] = video['poster']
            if video.get('description'):
                item['content_html'] += '<p>' + video['description'] + '</p>'
    if article_json.get('images'):
        image = utils.closest_dict(article_json['images'][0]['sourceSets'], 'width', 1200)
        item['_image'] = image['url']
        if not lede:
            item['content_html'] += utils.add_image(image['url'], article_json['images'][0].get('caption'))

    if 'embed' in args:
        item['content_html'] = '<div style="width:80%; margin-right:auto; margin-left:auto; border:1px solid black; border-radius:10px;">'
        if item.get('_image'):
            item['content_html'] += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(item['url'], item['_image'])
        item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(split_url.netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        item['content_html'] += '<p><a href="{}/content?read&url={}">Read</a></p></div></div>'.format(config.server, quote_plus(item['url']))
        return item

    for content in article_json['body']:
        for key, val in content.items():
            if key == 'p':
                if val.startswith('l '):
                    # lists? https://www.independent.ie/opinion/comment/fionnan-sheahan-the-ryan-tubridy-riddle-who-deliberately-doctored-digits-in-former-rte-stars-earnings/a1026891947.html
                    item['content_html'] += '<ul><li>' + val[2:] + '</li></ul>'
                else:
                    item['content_html'] += '<p>' + val + '</p>'
            elif key == 'subhead':
                item['content_html'] += '<h3>' + val + '</h3>'
            elif key == 'image':
                image = utils.closest_dict(val['sourceSets'], 'width', 1200)
                item['content_html'] += utils.add_image(image['url'], val.get('caption'))
            elif key == 'quote':
                item['content_html'] += utils.add_pullquote(val['text'])
                # item['content_html'] += utils.add_blockquote(val['text'])
            elif key == 'legacy-ml':
                soup = BeautifulSoup(val, 'html.parser')
                el = soup.find('div', class_=['pa-embed', 'flourish-embed'])
                if el:
                    if 'pa-embed' in el['class']:
                        if el['data-type'] == 'quote':
                            item['content_html'] += utils.add_pullquote(el['data-quote'], el.get('data-source'))
                        else:
                            logger.warning('unhandled pa-embed data-type {} in {}'.format(el['data-type'], item['url']))
                    elif 'flourish-embed' in el['class']:
                        item['content_html'] += utils.add_embed('https://flo.uri.sh/' + el['data-src'] + '/embed?auto=1')
                else:
                    logger.warning('unhandled legacy-ml content in ' + item['url'])
            elif key == 'ad' or key == 'related':
                pass
            else:
                logger.warning('unhandled content {} in {}'.format(key, item['url']))
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    gql_query = {
        "operationName": "webv2_Articles_{}_3_2".format(site_json['brand']),
        "variables": {
            "skip": 0,
            "brand": site_json['brand'],
            "sourcesetCroppingInput": {
                "resizeMode": "CENTER_CROP",
                "cropsMode": "LANDSCAPE",
                "fallbackResizeMode": "SMART_CROP",
                "sizes":[
                    {"key": "xsmall", "width": 120, "height": 80},
                    {"key": "small", "width": 160, "height": 107},
                    {"key": "smallMobile", "width": 240, "height": 160},
                    {"key": "medium", "width": 320, "height": 213},
                    {"key": "large", "width": 640, "height": 427},
                    {"key": "xlarge", "width": 960, "height": 640},
                    {"key": "xxlarge", "width": 1280, "height": 853}
                ]
            },
            "count": 10,
            "sections": ["9e931a6d-3e1c-4be0-874d-8f7d56c8f85f"],
            "ordering": "MOST_RECENT",
            "type": "article,interview,review,short,photoset,video",
            "usePagination": True,
            "resizeMode": "CENTER_CROP"
        },
        "query": '''
query webv2_Articles_beltel_3_2(
    $skip: Int
    $type: String
    $after: String
    $brand: String!
    $count: Int!
    $keywordIds: [ID!]
    $keywords: [String]
    $ordering: ArticlesSearchOrdering
    $sections: [ID!]
    $premium: Boolean
    $usePagination: Boolean!
    $webcmsIds: [ID!]
    $sourcesetCroppingInput: SourcesetCroppingInput
    $zipcode: String
    ) {
    articles: articlesSearch(
      skip: $skip
      type: $type
      brand: $brand
      count: $count
      keywordIds: $keywordIds
      keywords: $keywords
      ordering: $ordering
      sections: $sections
      premium: $premium
      webcmsIds: $webcmsIds
      zipcode: $zipcode
    ) @skip(if: $usePagination) {
      
    id
    articleBrand: brand
    teaser {
      title
      label
      
      
    }
    relativeUrl
    webcmsId
    articleType: type
    title
    subLabel: sublabel
    premium
    intro
    
      images {
        url
        id
        sourceSets(sourcesetCroppingInput: $sourcesetCroppingInput) {
          height
          key
          url
          width
        }
      }
      
    sections {
      name
      brand
      type
      sequence
    }
    keywords {
      name
    }
    publishedAt
    articleType: type
  

    }
    articlesConnection: articlesSearchConnection(
      type: $type
      after: $after
      brand: $brand
      first: $count
      keywordIds: $keywordIds
      keywords: $keywords
      ordering: $ordering
      sections: $sections
      premium: $premium
      webcmsIds: $webcmsIds
    ) @include(if: $usePagination) {
      pageInfo {
        endCursor
        hasNextPage
      }
      edges {
        node {
          
    id
    articleBrand: brand
    teaser {
      title
      label
      
      
    }
    relativeUrl
    webcmsId
    articleType: type
    title
    subLabel: sublabel
    premium
    intro
    
      images {
        url
        id
        sourceSets(sourcesetCroppingInput: $sourcesetCroppingInput) {
          height
          key
          url
          width
        }
      }
      
    sections {
      name
      brand
      type
      sequence
    }
    keywords {
      name
    }
    publishedAt
    articleType: type
  
        }
      }
    }
  }
    '''
    }
    gql_query = utils.post_url('{}://{}/graphql-blue-mhie'.format(split_url.scheme, split_url.netloc), json_data=gql_query)
    if not gql_query:
        return None
    if save_debug:
        utils.write_file(gql_query, './debug/feed.json')
