import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "dpr": "1",
        "referer": url,
        "sec-ch-ua": "\"Not?A_Brand\";v=\"8\", \"Chromium\";v=\"108\", \"Microsoft Edge\";v=\"108\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36 Edg/108.0.1462.46",
        "viewport-width": "1098"
    }
    data = '[{{\"operationName\":\"singlePostQuery\",\"variables\":{{\"input\":{{\"selector\":{{\"documentId\":\"{}\"}}}},\"sequenceId\":null}},\"query\":\"query singlePostQuery($input: SinglePostInput, $sequenceId: String) {{\\n  post(input: $input) {{\\n    result {{\\n      ...PostsWithNavigation\\n      __typename\\n    }}\\n    __typename\\n  }}\\n}}\\n\\nfragment PostsWithNavigation on Post {{\\n  ...PostsPage\\n  ...PostSequenceNavigation\\n  tableOfContents\\n  __typename\\n}}\\n\\nfragment PostsPage on Post {{\\n  ...PostsDetails\\n  version\\n  contents {{\\n    ...RevisionDisplay\\n    __typename\\n  }}\\n  myEditorAccess\\n  linkSharingKey\\n  __typename\\n}}\\n\\nfragment PostsDetails on Post {{\\n  ...PostsListBase\\n  canonicalSource\\n  noIndex\\n  viewCount\\n  socialPreviewImageUrl\\n  tagRelevance\\n  commentSortOrder\\n  sideCommentVisibility\\n  collectionTitle\\n  canonicalPrevPostSlug\\n  canonicalNextPostSlug\\n  canonicalSequenceId\\n  canonicalBookId\\n  canonicalSequence {{\\n    _id\\n    title\\n    __typename\\n  }}\\n  canonicalBook {{\\n    _id\\n    title\\n    __typename\\n  }}\\n  canonicalCollection {{\\n    _id\\n    title\\n    __typename\\n  }}\\n  podcastEpisode {{\\n    title\\n    podcast {{\\n      title\\n      applePodcastLink\\n      spotifyPodcastLink\\n      __typename\\n    }}\\n    episodeLink\\n    externalEpisodeId\\n    __typename\\n  }}\\n  showModerationGuidelines\\n  bannedUserIds\\n  moderationStyle\\n  currentUserVote\\n  currentUserExtendedVote\\n  feedLink\\n  feed {{\\n    ...RSSFeedMinimumInfo\\n    __typename\\n  }}\\n  sourcePostRelations {{\\n    _id\\n    sourcePostId\\n    sourcePost {{\\n      ...PostsList\\n      __typename\\n    }}\\n    order\\n    __typename\\n  }}\\n  targetPostRelations {{\\n    _id\\n    sourcePostId\\n    targetPostId\\n    targetPost {{\\n      ...PostsList\\n      __typename\\n    }}\\n    order\\n    __typename\\n  }}\\n  rsvps\\n  activateRSVPs\\n  fmCrosspost\\n  podcastEpisodeId\\n  __typename\\n}}\\n\\nfragment PostsListBase on Post {{\\n  ...PostsBase\\n  ...PostsAuthors\\n  readTimeMinutes\\n  moderationGuidelines {{\\n    _id\\n    html\\n    __typename\\n  }}\\n  customHighlight {{\\n    _id\\n    html\\n    __typename\\n  }}\\n  lastPromotedComment {{\\n    user {{\\n      ...UsersMinimumInfo\\n      __typename\\n    }}\\n    __typename\\n  }}\\n  bestAnswer {{\\n    ...CommentsList\\n    __typename\\n  }}\\n  tags {{\\n    ...TagPreviewFragment\\n    __typename\\n  }}\\n  __typename\\n}}\\n\\nfragment PostsBase on Post {{\\n  ...PostsMinimumInfo\\n  url\\n  postedAt\\n  createdAt\\n  sticky\\n  metaSticky\\n  stickyPriority\\n  status\\n  frontpageDate\\n  meta\\n  deletedDraft\\n  shareWithUsers\\n  sharingSettings\\n  coauthorStatuses\\n  hasCoauthorPermission\\n  commentCount\\n  voteCount\\n  baseScore\\n  extendedScore\\n  unlisted\\n  score\\n  lastVisitedAt\\n  isFuture\\n  isRead\\n  lastCommentedAt\\n  lastCommentPromotedAt\\n  canonicalCollectionSlug\\n  curatedDate\\n  commentsLocked\\n  commentsLockedToAccountsCreatedAfter\\n  question\\n  hiddenRelatedQuestion\\n  originalPostRelationSourceId\\n  userId\\n  location\\n  googleLocation\\n  onlineEvent\\n  globalEvent\\n  startTime\\n  endTime\\n  localStartTime\\n  localEndTime\\n  eventRegistrationLink\\n  joinEventLink\\n  facebookLink\\n  meetupLink\\n  website\\n  contactInfo\\n  isEvent\\n  eventImageId\\n  eventType\\n  types\\n  groupId\\n  reviewedByUserId\\n  suggestForCuratedUserIds\\n  suggestForCuratedUsernames\\n  reviewForCuratedUserId\\n  authorIsUnreviewed\\n  afDate\\n  suggestForAlignmentUserIds\\n  reviewForAlignmentUserId\\n  afBaseScore\\n  afExtendedScore\\n  afCommentCount\\n  afLastCommentedAt\\n  afSticky\\n  hideAuthor\\n  moderationStyle\\n  submitToFrontpage\\n  shortform\\n  onlyVisibleToLoggedIn\\n  reviewCount\\n  reviewVoteCount\\n  positiveReviewVoteCount\\n  reviewVoteScoreAllKarma\\n  reviewVotesAllKarma\\n  reviewVoteScoreHighKarma\\n  reviewVotesHighKarma\\n  reviewVoteScoreAF\\n  reviewVotesAF\\n  finalReviewVoteScoreHighKarma\\n  finalReviewVotesHighKarma\\n  finalReviewVoteScoreAllKarma\\n  finalReviewVotesAllKarma\\n  finalReviewVoteScoreAF\\n  finalReviewVotesAF\\n  group {{\\n    _id\\n    name\\n    organizerIds\\n    __typename\\n  }}\\n  nominationCount2018\\n  reviewCount2018\\n  nominationCount2019\\n  reviewCount2019\\n  __typename\\n}}\\n\\nfragment PostsMinimumInfo on Post {{\\n  _id\\n  slug\\n  title\\n  draft\\n  hideCommentKarma\\n  af\\n  currentUserReviewVote {{\\n    _id\\n    qualitativeScore\\n    __typename\\n  }}\\n  userId\\n  __typename\\n}}\\n\\nfragment PostsAuthors on Post {{\\n  user {{\\n    ...UsersMinimumInfo\\n    biography {{\\n      ...RevisionDisplay\\n      __typename\\n    }}\\n    profileImageId\\n    moderationStyle\\n    bannedUserIds\\n    moderatorAssistance\\n    __typename\\n  }}\\n  coauthors {{\\n    ...UsersMinimumInfo\\n    __typename\\n  }}\\n  __typename\\n}}\\n\\nfragment UsersMinimumInfo on User {{\\n  _id\\n  slug\\n  createdAt\\n  username\\n  displayName\\n  previousDisplayName\\n  fullName\\n  karma\\n  afKarma\\n  deleted\\n  isAdmin\\n  htmlBio\\n  postCount\\n  commentCount\\n  sequenceCount\\n  afPostCount\\n  afCommentCount\\n  spamRiskScore\\n  tagRevisionCount\\n  __typename\\n}}\\n\\nfragment RevisionDisplay on Revision {{\\n  _id\\n  version\\n  updateType\\n  editedAt\\n  userId\\n  html\\n  wordCount\\n  htmlHighlight\\n  plaintextDescription\\n  __typename\\n}}\\n\\nfragment CommentsList on Comment {{\\n  _id\\n  postId\\n  tagId\\n  tagCommentType\\n  parentCommentId\\n  topLevelCommentId\\n  descendentCount\\n  contents {{\\n    _id\\n    html\\n    plaintextMainText\\n    wordCount\\n    __typename\\n  }}\\n  postedAt\\n  repliesBlockedUntil\\n  userId\\n  deleted\\n  deletedPublic\\n  deletedReason\\n  hideAuthor\\n  user {{\\n    ...UsersMinimumInfo\\n    __typename\\n  }}\\n  currentUserVote\\n  currentUserExtendedVote\\n  baseScore\\n  extendedScore\\n  score\\n  voteCount\\n  af\\n  afDate\\n  moveToAlignmentUserId\\n  afBaseScore\\n  afExtendedScore\\n  suggestForAlignmentUserIds\\n  reviewForAlignmentUserId\\n  needsReview\\n  answer\\n  parentAnswerId\\n  retracted\\n  postVersion\\n  reviewedByUserId\\n  shortform\\n  lastSubthreadActivity\\n  moderatorHat\\n  hideModeratorHat\\n  nominatedForReview\\n  reviewingForReview\\n  promoted\\n  promotedByUser {{\\n    ...UsersMinimumInfo\\n    __typename\\n  }}\\n  directChildrenCount\\n  votingSystem\\n  isPinnedOnProfile\\n  __typename\\n}}\\n\\nfragment TagPreviewFragment on Tag {{\\n  ...TagBasicInfo\\n  parentTag {{\\n    _id\\n    name\\n    slug\\n    __typename\\n  }}\\n  subTags {{\\n    _id\\n    name\\n    slug\\n    __typename\\n  }}\\n  description {{\\n    _id\\n    htmlHighlight\\n    __typename\\n  }}\\n  __typename\\n}}\\n\\nfragment TagBasicInfo on Tag {{\\n  _id\\n  userId\\n  name\\n  slug\\n  core\\n  postCount\\n  adminOnly\\n  canEditUserIds\\n  suggestedAsFilter\\n  needsReview\\n  descriptionTruncationCount\\n  createdAt\\n  wikiOnly\\n  deleted\\n  __typename\\n}}\\n\\nfragment RSSFeedMinimumInfo on RSSFeed {{\\n  _id\\n  userId\\n  user {{\\n    ...UsersMinimumInfo\\n    __typename\\n  }}\\n  createdAt\\n  ownedByUser\\n  displayFullContent\\n  nickname\\n  url\\n  __typename\\n}}\\n\\nfragment PostsList on Post {{\\n  ...PostsListBase\\n  deletedDraft\\n  contents {{\\n    _id\\n    htmlHighlight\\n    wordCount\\n    version\\n    __typename\\n  }}\\n  fmCrosspost\\n  __typename\\n}}\\n\\nfragment PostSequenceNavigation on Post {{\\n  sequence(sequenceId: $sequenceId) {{\\n    ...SequencesPageFragment\\n    __typename\\n  }}\\n  prevPost(sequenceId: $sequenceId) {{\\n    _id\\n    title\\n    slug\\n    commentCount\\n    baseScore\\n    sequence(sequenceId: $sequenceId, prevOrNext: \\\"prev\\\") {{\\n      _id\\n      __typename\\n    }}\\n    __typename\\n  }}\\n  nextPost(sequenceId: $sequenceId) {{\\n    _id\\n    title\\n    slug\\n    commentCount\\n    baseScore\\n    sequence(sequenceId: $sequenceId, prevOrNext: \\\"next\\\") {{\\n      _id\\n      __typename\\n    }}\\n    __typename\\n  }}\\n  __typename\\n}}\\n\\nfragment SequencesPageFragment on Sequence {{\\n  ...SequencesPageTitleFragment\\n  createdAt\\n  userId\\n  user {{\\n    ...UsersMinimumInfo\\n    __typename\\n  }}\\n  contents {{\\n    ...RevisionDisplay\\n    __typename\\n  }}\\n  gridImageId\\n  bannerImageId\\n  canonicalCollectionSlug\\n  draft\\n  isDeleted\\n  hidden\\n  hideFromAuthorPage\\n  curatedOrder\\n  userProfileOrder\\n  af\\n  __typename\\n}}\\n\\nfragment SequencesPageTitleFragment on Sequence {{\\n  _id\\n  title\\n  canonicalCollectionSlug\\n  canonicalCollection {{\\n    title\\n    __typename\\n  }}\\n  __typename\\n}}\\n\"}}]'.format(paths[1])
    gql_json = utils.post_url('https://{}/graphql'.format(split_url.netloc), data=data, headers=headers)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')
    post_json = gql_json[0]['data']['post']['result']

    item = {}
    item['id'] = post_json['_id']
    item['url'] = url
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['postedAt'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if post_json['contents'].get('editedAt'):
        dt = datetime.fromisoformat(post_json['contents']['editedAt'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()

    authors = []
    authors.append(post_json['user']['displayName'])
    if post_json.get('coauthors'):
        for it in post_json['coauthors']:
            authors.append(it['displayName'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if post_json.get('tags'):
        item['tags'] = []
        for it in post_json['tags']:
            item['tags'].append(it['name'])

    if post_json['contents'].get('plaintextDescription'):
        item['summary'] = post_json['contents']['plaintextDescription']

    soup = BeautifulSoup(post_json['contents']['html'], 'html.parser')
    for el in soup.find_all('img'):
        new_html = ''
        if el.get('srcset'):
            img_src = utils.image_from_srcset(el['srcset'], 1000)
        else:
            img_src = el['src']
        caption = ''
        if el.parent and el.parent.name == 'figure':
            if el.parent.figcaption:
                caption = el.parent.figcaption.decode_contents()
        new_html = utils.add_image(img_src, caption)
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            if el.parent and el.parent.name == 'figure':
                el.parent.insert_after(new_el)
                el.parent.decompose()
            else:
                el.insert_after(new_el)
                el.decompose()
        else:
            logger.warning('unhandled figure image in ' + item['url'])

    for el in soup.find_all('blockquote'):
        el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

    item['content_html'] = ''
    if post_json.get('url'):
        item['content_html'] += '<p><em>This is a linkpost from <a href="{0}">{0}</a></em></p>'.format(post_json['url'])
    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    if 'feed.xml' in args['url']:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path[1:].split('/')))

    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "dpr": "1",
        "referer": args['url'],
        "sec-ch-ua": "\"Not?A_Brand\";v=\"8\", \"Chromium\";v=\"108\", \"Microsoft Edge\";v=\"108\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36 Edg/108.0.1462.46",
        "viewport-width": "1098"
    }
    gql_url = 'https://{}/graphql'.format(split_url.netloc)
    if paths[0] == 'users':
        data = '[{{\"operationName\":\"multiUserQuery\",\"variables\":{{\"input\":{{\"terms\":{{\"view\":\"usersProfile\",\"slug\":\"{}\",\"limit\":10}},\"enableCache\":false,\"enableTotal\":false}}}},\"query\":\"query multiUserQuery($input: MultiUserInput) {{\\n  users(input: $input) {{\\n    results {{\\n      ...UsersMinimumInfo\\n      __typename\\n    }}\\n    totalCount\\n    __typename\\n  }}\\n}}\\n\\nfragment UsersMinimumInfo on User {{\\n  _id\\n  slug\\n  createdAt\\n  username\\n  displayName\\n  previousDisplayName\\n  fullName\\n  karma\\n  afKarma\\n  deleted\\n  isAdmin\\n  htmlBio\\n  postCount\\n  commentCount\\n  sequenceCount\\n  afPostCount\\n  afCommentCount\\n  spamRiskScore\\n  tagRevisionCount\\n  __typename\\n}}\\n\"}}]'.format(paths[1])
        gql_json = utils.post_url(gql_url, data=data, headers=headers)
        if not gql_json:
            return None
        user_id = gql_json[0]['data']['users']['results'][0]['_id']
        user_name = gql_json[0]['data']['users']['results'][0]['username']
        feed_title = '{} | {}'.format(split_url.netloc, user_name)
        data = '[{{\"operationName\":\"multiPostQuery\",\"variables\":{{\"input\":{{\"terms\":{{\"view\":\"userPosts\",\"userId\":\"{}\",\"authorIsUnreviewed\":null,\"excludeEvents\":true,\"limit\":10}},\"enableCache\":false,\"enableTotal\":false}}}},\"query\":\"query multiPostQuery($input: MultiPostInput) {{\\n  posts(input: $input) {{\\n    results {{\\n      ...PostsList\\n      __typename\\n    }}\\n    totalCount\\n    __typename\\n  }}\\n}}\\n\\nfragment PostsList on Post {{\\n  ...PostsListBase\\n  deletedDraft\\n  contents {{\\n    _id\\n    htmlHighlight\\n    wordCount\\n    version\\n    __typename\\n  }}\\n  fmCrosspost\\n  __typename\\n}}\\n\\nfragment PostsListBase on Post {{\\n  ...PostsBase\\n  ...PostsAuthors\\n  readTimeMinutes\\n  moderationGuidelines {{\\n    _id\\n    html\\n    __typename\\n  }}\\n  customHighlight {{\\n    _id\\n    html\\n    __typename\\n  }}\\n  lastPromotedComment {{\\n    user {{\\n      ...UsersMinimumInfo\\n      __typename\\n    }}\\n    __typename\\n  }}\\n  bestAnswer {{\\n    ...CommentsList\\n    __typename\\n  }}\\n  tags {{\\n    ...TagPreviewFragment\\n    __typename\\n  }}\\n  __typename\\n}}\\n\\nfragment PostsBase on Post {{\\n  ...PostsMinimumInfo\\n  url\\n  postedAt\\n  createdAt\\n  sticky\\n  metaSticky\\n  stickyPriority\\n  status\\n  frontpageDate\\n  meta\\n  deletedDraft\\n  shareWithUsers\\n  sharingSettings\\n  coauthorStatuses\\n  hasCoauthorPermission\\n  commentCount\\n  voteCount\\n  baseScore\\n  extendedScore\\n  unlisted\\n  score\\n  lastVisitedAt\\n  isFuture\\n  isRead\\n  lastCommentedAt\\n  lastCommentPromotedAt\\n  canonicalCollectionSlug\\n  curatedDate\\n  commentsLocked\\n  commentsLockedToAccountsCreatedAfter\\n  question\\n  hiddenRelatedQuestion\\n  originalPostRelationSourceId\\n  userId\\n  location\\n  googleLocation\\n  onlineEvent\\n  globalEvent\\n  startTime\\n  endTime\\n  localStartTime\\n  localEndTime\\n  eventRegistrationLink\\n  joinEventLink\\n  facebookLink\\n  meetupLink\\n  website\\n  contactInfo\\n  isEvent\\n  eventImageId\\n  eventType\\n  types\\n  groupId\\n  reviewedByUserId\\n  suggestForCuratedUserIds\\n  suggestForCuratedUsernames\\n  reviewForCuratedUserId\\n  authorIsUnreviewed\\n  afDate\\n  suggestForAlignmentUserIds\\n  reviewForAlignmentUserId\\n  afBaseScore\\n  afExtendedScore\\n  afCommentCount\\n  afLastCommentedAt\\n  afSticky\\n  hideAuthor\\n  moderationStyle\\n  submitToFrontpage\\n  shortform\\n  onlyVisibleToLoggedIn\\n  reviewCount\\n  reviewVoteCount\\n  positiveReviewVoteCount\\n  reviewVoteScoreAllKarma\\n  reviewVotesAllKarma\\n  reviewVoteScoreHighKarma\\n  reviewVotesHighKarma\\n  reviewVoteScoreAF\\n  reviewVotesAF\\n  finalReviewVoteScoreHighKarma\\n  finalReviewVotesHighKarma\\n  finalReviewVoteScoreAllKarma\\n  finalReviewVotesAllKarma\\n  finalReviewVoteScoreAF\\n  finalReviewVotesAF\\n  group {{\\n    _id\\n    name\\n    organizerIds\\n    __typename\\n  }}\\n  nominationCount2018\\n  reviewCount2018\\n  nominationCount2019\\n  reviewCount2019\\n  __typename\\n}}\\n\\nfragment PostsMinimumInfo on Post {{\\n  _id\\n  slug\\n  title\\n  draft\\n  hideCommentKarma\\n  af\\n  currentUserReviewVote {{\\n    _id\\n    qualitativeScore\\n    __typename\\n  }}\\n  userId\\n  __typename\\n}}\\n\\nfragment PostsAuthors on Post {{\\n  user {{\\n    ...UsersMinimumInfo\\n    biography {{\\n      ...RevisionDisplay\\n      __typename\\n    }}\\n    profileImageId\\n    moderationStyle\\n    bannedUserIds\\n    moderatorAssistance\\n    __typename\\n  }}\\n  coauthors {{\\n    ...UsersMinimumInfo\\n    __typename\\n  }}\\n  __typename\\n}}\\n\\nfragment UsersMinimumInfo on User {{\\n  _id\\n  slug\\n  createdAt\\n  username\\n  displayName\\n  previousDisplayName\\n  fullName\\n  karma\\n  afKarma\\n  deleted\\n  isAdmin\\n  htmlBio\\n  postCount\\n  commentCount\\n  sequenceCount\\n  afPostCount\\n  afCommentCount\\n  spamRiskScore\\n  tagRevisionCount\\n  __typename\\n}}\\n\\nfragment RevisionDisplay on Revision {{\\n  _id\\n  version\\n  updateType\\n  editedAt\\n  userId\\n  html\\n  wordCount\\n  htmlHighlight\\n  plaintextDescription\\n  __typename\\n}}\\n\\nfragment CommentsList on Comment {{\\n  _id\\n  postId\\n  tagId\\n  tagCommentType\\n  parentCommentId\\n  topLevelCommentId\\n  descendentCount\\n  contents {{\\n    _id\\n    html\\n    plaintextMainText\\n    wordCount\\n    __typename\\n  }}\\n  postedAt\\n  repliesBlockedUntil\\n  userId\\n  deleted\\n  deletedPublic\\n  deletedReason\\n  hideAuthor\\n  user {{\\n    ...UsersMinimumInfo\\n    __typename\\n  }}\\n  currentUserVote\\n  currentUserExtendedVote\\n  baseScore\\n  extendedScore\\n  score\\n  voteCount\\n  af\\n  afDate\\n  moveToAlignmentUserId\\n  afBaseScore\\n  afExtendedScore\\n  suggestForAlignmentUserIds\\n  reviewForAlignmentUserId\\n  needsReview\\n  answer\\n  parentAnswerId\\n  retracted\\n  postVersion\\n  reviewedByUserId\\n  shortform\\n  lastSubthreadActivity\\n  moderatorHat\\n  hideModeratorHat\\n  nominatedForReview\\n  reviewingForReview\\n  promoted\\n  promotedByUser {{\\n    ...UsersMinimumInfo\\n    __typename\\n  }}\\n  directChildrenCount\\n  votingSystem\\n  isPinnedOnProfile\\n  __typename\\n}}\\n\\nfragment TagPreviewFragment on Tag {{\\n  ...TagBasicInfo\\n  parentTag {{\\n    _id\\n    name\\n    slug\\n    __typename\\n  }}\\n  subTags {{\\n    _id\\n    name\\n    slug\\n    __typename\\n  }}\\n  description {{\\n    _id\\n    htmlHighlight\\n    __typename\\n  }}\\n  __typename\\n}}\\n\\nfragment TagBasicInfo on Tag {{\\n  _id\\n  userId\\n  name\\n  slug\\n  core\\n  postCount\\n  adminOnly\\n  canEditUserIds\\n  suggestedAsFilter\\n  needsReview\\n  descriptionTruncationCount\\n  createdAt\\n  wikiOnly\\n  deleted\\n  __typename\\n}}\\n\"}}]'.format(user_id)
        gql_json = utils.post_url(gql_url, data=data, headers=headers)
        if not gql_json:
            return None
        if save_debug:
            utils.write_file(gql_json, './debug/feed.json')
        posts = gql_json[0]['data']['posts']['results']
    elif paths[0] == 'tag':
        data = '[{{\"operationName\":\"multiTagQuery\",\"variables\":{{\"input\":{{\"terms\":{{\"view\":\"tagBySlug\",\"slug\":\"{}\",\"limit\":1}},\"enableCache\":false,\"enableTotal\":false}}}},\"query\":\"query multiTagQuery($input: MultiTagInput) {{\\n  tags(input: $input) {{\\n    results {{\\n      ...TagFragment\\n      __typename\\n    }}\\n    totalCount\\n    __typename\\n  }}\\n}}\\n\\nfragment TagFragment on Tag {{\\n  ...TagDetailsFragment\\n  parentTag {{\\n    _id\\n    name\\n    slug\\n    __typename\\n  }}\\n  subTags {{\\n    _id\\n    name\\n    slug\\n    __typename\\n  }}\\n  description {{\\n    _id\\n    html\\n    htmlHighlight\\n    plaintextDescription\\n    version\\n    __typename\\n  }}\\n  __typename\\n}}\\n\\nfragment TagDetailsFragment on Tag {{\\n  ...TagBasicInfo\\n  oldSlugs\\n  isRead\\n  defaultOrder\\n  reviewedByUserId\\n  wikiGrade\\n  isSubforum\\n  subforumModeratorIds\\n  subforumModerators {{\\n    ...UsersMinimumInfo\\n    __typename\\n  }}\\n  moderationGuidelines {{\\n    _id\\n    html\\n    __typename\\n  }}\\n  bannerImageId\\n  lesswrongWikiImportSlug\\n  lesswrongWikiImportRevision\\n  sequence {{\\n    ...SequencesPageFragment\\n    __typename\\n  }}\\n  __typename\\n}}\\n\\nfragment TagBasicInfo on Tag {{\\n  _id\\n  userId\\n  name\\n  slug\\n  core\\n  postCount\\n  adminOnly\\n  canEditUserIds\\n  suggestedAsFilter\\n  needsReview\\n  descriptionTruncationCount\\n  createdAt\\n  wikiOnly\\n  deleted\\n  __typename\\n}}\\n\\nfragment UsersMinimumInfo on User {{\\n  _id\\n  slug\\n  createdAt\\n  username\\n  displayName\\n  previousDisplayName\\n  fullName\\n  karma\\n  afKarma\\n  deleted\\n  isAdmin\\n  htmlBio\\n  postCount\\n  commentCount\\n  sequenceCount\\n  afPostCount\\n  afCommentCount\\n  spamRiskScore\\n  tagRevisionCount\\n  __typename\\n}}\\n\\nfragment SequencesPageFragment on Sequence {{\\n  ...SequencesPageTitleFragment\\n  createdAt\\n  userId\\n  user {{\\n    ...UsersMinimumInfo\\n    __typename\\n  }}\\n  contents {{\\n    ...RevisionDisplay\\n    __typename\\n  }}\\n  gridImageId\\n  bannerImageId\\n  canonicalCollectionSlug\\n  draft\\n  isDeleted\\n  hidden\\n  hideFromAuthorPage\\n  curatedOrder\\n  userProfileOrder\\n  af\\n  __typename\\n}}\\n\\nfragment SequencesPageTitleFragment on Sequence {{\\n  _id\\n  title\\n  canonicalCollectionSlug\\n  canonicalCollection {{\\n    title\\n    __typename\\n  }}\\n  __typename\\n}}\\n\\nfragment RevisionDisplay on Revision {{\\n  _id\\n  version\\n  updateType\\n  editedAt\\n  userId\\n  html\\n  wordCount\\n  htmlHighlight\\n  plaintextDescription\\n  __typename\\n}}\\n\"}}]'.format(paths[1])
        gql_json = utils.post_url(gql_url, data=data, headers=headers)
        if not gql_json:
            return None
        tag_id = gql_json[0]['data']['tags']['results'][0]['_id']
        tag_name = gql_json[0]['data']['tags']['results'][0]['name']
        feed_title = '{} | {}'.format(split_url.netloc, tag_name)
        data = '[{{\"operationName\":\"multiPostQuery\",\"variables\":{{\"input\":{{\"terms\":{{\"sortedBy\":\"new\",\"filterSettings\":{{\"tags\":[{{\"tagId\":\"{}\",\"tagName\":\"{}\",\"filterMode\":\"Required\"}}]}},\"view\":\"tagRelevance\",\"tagId\":\"zFrdtg6wCuzWu6mhy\",\"limit\":15}},\"enableCache\":false,\"enableTotal\":true}},\"tagId\":\"zFrdtg6wCuzWu6mhy\"}},\"query\":\"query multiPostQuery($input: MultiPostInput, $tagId: String) {{\\n  posts(input: $input) {{\\n    results {{\\n      ...PostsListTag\\n      __typename\\n    }}\\n    totalCount\\n    __typename\\n  }}\\n}}\\n\\nfragment PostsListTag on Post {{\\n  ...PostsList\\n  tagRelevance\\n  tagRel(tagId: $tagId) {{\\n    ...WithVoteTagRel\\n    __typename\\n  }}\\n  __typename\\n}}\\n\\nfragment PostsList on Post {{\\n  ...PostsListBase\\n  deletedDraft\\n  contents {{\\n    _id\\n    htmlHighlight\\n    wordCount\\n    version\\n    __typename\\n  }}\\n  fmCrosspost\\n  __typename\\n}}\\n\\nfragment PostsListBase on Post {{\\n  ...PostsBase\\n  ...PostsAuthors\\n  readTimeMinutes\\n  moderationGuidelines {{\\n    _id\\n    html\\n    __typename\\n  }}\\n  customHighlight {{\\n    _id\\n    html\\n    __typename\\n  }}\\n  lastPromotedComment {{\\n    user {{\\n      ...UsersMinimumInfo\\n      __typename\\n    }}\\n    __typename\\n  }}\\n  bestAnswer {{\\n    ...CommentsList\\n    __typename\\n  }}\\n  tags {{\\n    ...TagPreviewFragment\\n    __typename\\n  }}\\n  __typename\\n}}\\n\\nfragment PostsBase on Post {{\\n  ...PostsMinimumInfo\\n  url\\n  postedAt\\n  createdAt\\n  sticky\\n  metaSticky\\n  stickyPriority\\n  status\\n  frontpageDate\\n  meta\\n  deletedDraft\\n  shareWithUsers\\n  sharingSettings\\n  coauthorStatuses\\n  hasCoauthorPermission\\n  commentCount\\n  voteCount\\n  baseScore\\n  extendedScore\\n  unlisted\\n  score\\n  lastVisitedAt\\n  isFuture\\n  isRead\\n  lastCommentedAt\\n  lastCommentPromotedAt\\n  canonicalCollectionSlug\\n  curatedDate\\n  commentsLocked\\n  commentsLockedToAccountsCreatedAfter\\n  question\\n  hiddenRelatedQuestion\\n  originalPostRelationSourceId\\n  userId\\n  location\\n  googleLocation\\n  onlineEvent\\n  globalEvent\\n  startTime\\n  endTime\\n  localStartTime\\n  localEndTime\\n  eventRegistrationLink\\n  joinEventLink\\n  facebookLink\\n  meetupLink\\n  website\\n  contactInfo\\n  isEvent\\n  eventImageId\\n  eventType\\n  types\\n  groupId\\n  reviewedByUserId\\n  suggestForCuratedUserIds\\n  suggestForCuratedUsernames\\n  reviewForCuratedUserId\\n  authorIsUnreviewed\\n  afDate\\n  suggestForAlignmentUserIds\\n  reviewForAlignmentUserId\\n  afBaseScore\\n  afExtendedScore\\n  afCommentCount\\n  afLastCommentedAt\\n  afSticky\\n  hideAuthor\\n  moderationStyle\\n  submitToFrontpage\\n  shortform\\n  onlyVisibleToLoggedIn\\n  reviewCount\\n  reviewVoteCount\\n  positiveReviewVoteCount\\n  reviewVoteScoreAllKarma\\n  reviewVotesAllKarma\\n  reviewVoteScoreHighKarma\\n  reviewVotesHighKarma\\n  reviewVoteScoreAF\\n  reviewVotesAF\\n  finalReviewVoteScoreHighKarma\\n  finalReviewVotesHighKarma\\n  finalReviewVoteScoreAllKarma\\n  finalReviewVotesAllKarma\\n  finalReviewVoteScoreAF\\n  finalReviewVotesAF\\n  group {{\\n    _id\\n    name\\n    organizerIds\\n    __typename\\n  }}\\n  nominationCount2018\\n  reviewCount2018\\n  nominationCount2019\\n  reviewCount2019\\n  __typename\\n}}\\n\\nfragment PostsMinimumInfo on Post {{\\n  _id\\n  slug\\n  title\\n  draft\\n  hideCommentKarma\\n  af\\n  currentUserReviewVote {{\\n    _id\\n    qualitativeScore\\n    __typename\\n  }}\\n  userId\\n  __typename\\n}}\\n\\nfragment PostsAuthors on Post {{\\n  user {{\\n    ...UsersMinimumInfo\\n    biography {{\\n      ...RevisionDisplay\\n      __typename\\n    }}\\n    profileImageId\\n    moderationStyle\\n    bannedUserIds\\n    moderatorAssistance\\n    __typename\\n  }}\\n  coauthors {{\\n    ...UsersMinimumInfo\\n    __typename\\n  }}\\n  __typename\\n}}\\n\\nfragment UsersMinimumInfo on User {{\\n  _id\\n  slug\\n  createdAt\\n  username\\n  displayName\\n  previousDisplayName\\n  fullName\\n  karma\\n  afKarma\\n  deleted\\n  isAdmin\\n  htmlBio\\n  postCount\\n  commentCount\\n  sequenceCount\\n  afPostCount\\n  afCommentCount\\n  spamRiskScore\\n  tagRevisionCount\\n  __typename\\n}}\\n\\nfragment RevisionDisplay on Revision {{\\n  _id\\n  version\\n  updateType\\n  editedAt\\n  userId\\n  html\\n  wordCount\\n  htmlHighlight\\n  plaintextDescription\\n  __typename\\n}}\\n\\nfragment CommentsList on Comment {{\\n  _id\\n  postId\\n  tagId\\n  tagCommentType\\n  parentCommentId\\n  topLevelCommentId\\n  descendentCount\\n  contents {{\\n    _id\\n    html\\n    plaintextMainText\\n    wordCount\\n    __typename\\n  }}\\n  postedAt\\n  repliesBlockedUntil\\n  userId\\n  deleted\\n  deletedPublic\\n  deletedReason\\n  hideAuthor\\n  user {{\\n    ...UsersMinimumInfo\\n    __typename\\n  }}\\n  currentUserVote\\n  currentUserExtendedVote\\n  baseScore\\n  extendedScore\\n  score\\n  voteCount\\n  af\\n  afDate\\n  moveToAlignmentUserId\\n  afBaseScore\\n  afExtendedScore\\n  suggestForAlignmentUserIds\\n  reviewForAlignmentUserId\\n  needsReview\\n  answer\\n  parentAnswerId\\n  retracted\\n  postVersion\\n  reviewedByUserId\\n  shortform\\n  lastSubthreadActivity\\n  moderatorHat\\n  hideModeratorHat\\n  nominatedForReview\\n  reviewingForReview\\n  promoted\\n  promotedByUser {{\\n    ...UsersMinimumInfo\\n    __typename\\n  }}\\n  directChildrenCount\\n  votingSystem\\n  isPinnedOnProfile\\n  __typename\\n}}\\n\\nfragment TagPreviewFragment on Tag {{\\n  ...TagBasicInfo\\n  parentTag {{\\n    _id\\n    name\\n    slug\\n    __typename\\n  }}\\n  subTags {{\\n    _id\\n    name\\n    slug\\n    __typename\\n  }}\\n  description {{\\n    _id\\n    htmlHighlight\\n    __typename\\n  }}\\n  __typename\\n}}\\n\\nfragment TagBasicInfo on Tag {{\\n  _id\\n  userId\\n  name\\n  slug\\n  core\\n  postCount\\n  adminOnly\\n  canEditUserIds\\n  suggestedAsFilter\\n  needsReview\\n  descriptionTruncationCount\\n  createdAt\\n  wikiOnly\\n  deleted\\n  __typename\\n}}\\n\\nfragment WithVoteTagRel on TagRel {{\\n  __typename\\n  _id\\n  userId\\n  score\\n  baseScore\\n  extendedScore\\n  afBaseScore\\n  voteCount\\n  currentUserVote\\n  currentUserExtendedVote\\n}}\\n\"}}]'.format(tag_id, tag_name)
        gql_json = utils.post_url(gql_url, data=data, headers=headers)
        if not gql_json:
            return None
        if save_debug:
            utils.write_file(gql_json, './debug/feed.json')
        posts = gql_json[0]['data']['posts']['results']
    else:
        logger.warning('unhandled url ' + args['url'])
        return None

    n = 0
    feed_items = []
    for post in posts:
        url = '{}://{}/posts/{}/{}'.format(split_url.scheme, split_url.netloc, post['_id'], post['slug'])
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args and n == int(args['max']):
                    break

    feed = utils.init_jsonfeed(args)
    feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
