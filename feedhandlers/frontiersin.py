import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

from feedhandlers import dirt
import config, utils

import logging

logger = logging.getLogger(__name__)


def get_article(url, args, site_json, save_debug=False):
    # TODO: spaceId & acceptedStageId values
    gql_data = {
        "operationName": "Article",
        "variables": {
            "doi": "10.3389/fendo.2025.1505808",
            "spaceId": '??',
            "acceptedStageId": '??',
            "articleAllowedStagesIds": [],
            "acceptedArticleExcludedJournalIds": []
        },
        "query": "\n  query Article(\n    $doi: String!\n    $spaceId: smallint!\n    $acceptedStageId: Int!\n    $articleAllowedStagesIds: [Int!]\n    $acceptedArticleExcludedJournalIds: [Int!]\n  ) {\n    articles(\n      offset: 0\n      limit: 1\n      where: {\n        spaceId: { _eq: $spaceId }\n        doi: { _eq: $doi }\n        _or: [\n          { stage: { id: { _in: $articleAllowedStagesIds } } }\n          {\n            _and: [\n              { stage: { id: { _in: [$acceptedStageId] } } }\n              {\n                journalSectionPath: {\n                  journalId: { _nin: $acceptedArticleExcludedJournalIds }\n                }\n              }\n            ]\n          }\n        ]\n      }\n    ) {\n      doi\n      id\n      title\n      publishedArticle {\n        id\n        articleTypeId\n        articleTypeName\n        title\n        abstract\n        isPublished\n        authors(order_by: { order: asc }) {\n          id\n          lastName\n          givenNames\n          isCorresponding\n          affiliations {\n            organizationName\n            countryName\n          }\n          user {\n            id\n            isProfilePublic\n          }\n        }\n        contents {\n          html\n          type {\n            code\n          }\n        }\n        files {\n          name\n          fileServerPackageEntryId\n          type {\n            name\n            code\n          }\n        }\n        keywords {\n          keyword {\n            value\n          }\n        }\n        publicationDate\n      }\n      stage {\n        name\n        id\n      }\n      researchTopic {\n        id\n        title\n        articles_aggregate(\n          where: {\n            _or: [\n              { stage: { id: { _in: $articleAllowedStagesIds } } }\n              {\n                _and: [\n                  { stage: { id: { _in: [$acceptedStageId] } } }\n                  {\n                    journalSectionPath: {\n                      journalId: { _nin: $acceptedArticleExcludedJournalIds }\n                    }\n                  }\n                ]\n              }\n            ]\n          }\n        ) {\n          aggregate {\n            count\n          }\n        }\n      }\n      acceptanceDate\n      receptionDate\n      articleType {\n        id\n        name\n      }\n      journalSectionPath {\n        journal {\n          id\n          slug\n          electronicISSN\n          name\n          shortName\n          field {\n            id\n            domainId\n          }\n          specialtyId\n        }\n        section {\n          id\n          name\n          slug\n          specialtyId\n        }\n      }\n      impactData {\n        human_amount\n        action {\n          id\n          name\n        }\n      }\n      authors(order_by: { order: asc }) {\n        id\n        lastName\n        firstName\n        middleName\n        isCorresponding\n        emailAddress {\n          userId\n        }\n        affiliations(order_by: { order: asc }) {\n          id\n          organization {\n            name\n            addresses {\n              country {\n                name\n              }\n              cityName\n              zipCode\n              stateName\n            }\n          }\n        }\n      }\n      editors(\n        where: {\n          user: { isSuspended: { _eq: false } }\n          reviewAssignmentStatusId: { _in: [1, 2] }\n        }\n      ) {\n        user {\n          id\n          isProfilePublic\n          firstName\n          middleName\n          lastName\n          userAffiliations(where: { isPrimary: { _eq: true } }) {\n            organization {\n              name\n              addresses {\n                cityName\n                country {\n                  name\n                }\n              }\n            }\n          }\n        }\n      }\n      reviewers(\n        where: {\n          user: { isSuspended: { _eq: false } }\n          reviewAssignmentStatusId: { _in: [1, 2] }\n        }\n      ) {\n        user {\n          id\n          isProfilePublic\n          firstName\n          middleName\n          lastName\n          userAffiliations(where: { isPrimary: { _eq: true } }) {\n            organization {\n              name\n              addresses {\n                cityName\n                country {\n                  name\n                }\n              }\n            }\n          }\n        }\n      }\n      abstract\n    }\n  }\n"
    }
    # gql_url = frontiersGraphUrl



def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if 'news' not in paths:
        logger.warning('unhandled url ' + url)
        return None

    gql_data = {
        "operationName": "POST_BY_SLUG",
        "variables": {
            "slug": paths[-1],
            "preview": True
        },
        "query": '''
  query POST_BY_SLUG($slug: String, $preview: Boolean) {
    pageBlogPostCollection(
      limit: 1
      where: { slug: $slug }
      preview: $preview
    ) {
      items {
        title
        slug
        publishedOn
        excerpt
        featuredMedia {
          url
        }
        sys {
          publishedAt
        }
        relatedContentCollection(limit: 3) {
          items {
            title
            slug
            publishedOn
            featuredMedia {
              url
              description
            }
          }
        }
        categoriesCollection {
          items {
            slug
            name
          }
        }
        tagsCollection {
          items {
            name
            slug
          }
        }
        author {
          name
          slug
          role
          image {
            title
            description
            url
          }
        }
        featuredMedia {
          description
          url
        }
        autoInjectFeaturedImage
        content {
          json
          links {
            assets {
              __typename
              block {
                sys {
                  id
                }
                url
                description
                contentType
              }
            }
            entries {
              inline {
                __typename
                sys {
                  id
                }
              }
              block {
                __typename
                sys {
                  id
                }
                ...ComponentCustomLink
                ...ComponentSocialMedia
                ...ComponentGrid
                ...ComponentImageLink
                ...ComponentVideo
              }
            }
          }
        }
      }
    }
  }
  fragment ComponentCustomLink on ComponentCustomLink {
    icon
    color
    type
    size
    link {
      text
      url
      target
      ariaLabel
    }
  }
  fragment ComponentGrid on ComponentGrid {
    layout
    type
    itemsCollection {
      total
      items {
        ...ComponentCardRt
        ...ComponentCardRtDownload
      }
    }
  }
  fragment ComponentCardRt on ComponentCardRt {
    title
    text
    authors
    image {
      title
      description
      url
    }
    totalViews
    totalArticles
    cardLinkUrl
  }
  fragment ComponentCardRtDownload on ComponentCardRtDownload {
    title
    authors
    cardLinkUrl
    downloadLinkUrl
  }
  fragment ComponentImageLink on ComponentImageLink {
    url
    target
    ariaLabel
    image {
      title
      description
      url
    }
  }
  fragment ComponentVideo on ComponentVideo {
    provider
    url
    ratio
    controls
    autoplay
    mute
    subtitles
    caption
    asset {
      url
    }
  }
  fragment ComponentSocialMedia on ComponentSocialMedia {
    provider
    url
  }
'''
    }
    gql_url = 'https://graphql.contentful.com/content/v1/spaces/mrbo2ykgx5lt/environments/master'
    headers = {
        "authorization": site_json['auth']
    }
    gql_json = utils.post_url(gql_url, json_data=gql_data, headers=headers)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')

    post_json = gql_json['data']['pageBlogPostCollection']['items'][0]
    item = {}
    item['id'] = post_json['slug']
    item['url'] = url
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['publishedOn'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {
        "name": post_json['author']['name']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    item['tags'] = []
    if post_json['categoriesCollection'].get('items'):
        item['tags'] += [x['name'] for x in post_json['categoriesCollection']['items']]
    if post_json['tagsCollection'].get('items'):
        item['tags'] += [x['name'] for x in post_json['tagsCollection']['items']]

    if post_json.get('excerpt'):
        item['summary'] = post_json['excerpt']

    item['content_html'] = ''
    if post_json.get('featuredMedia'):
        item['image'] = post_json['featuredMedia']['url']
        item['content_html'] += utils.add_image(item['image'], post_json['featuredMedia'].get('description'))
        for block in post_json['content']['json']['content']:
            if block['nodeType'] == 'embedded-asset-block' and block['data']['target']['sys']['id'] in item['image']:
                item['content_html'] = ''

    item['content_html'] += dirt.render_content(post_json['content']['json'], post_json['content']['links'])

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item
