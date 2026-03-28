from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.cache import cache
from django.conf import settings
from .models import *

import os
import requests
import logging
import concurrent.futures
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

print(settings.GITHUB_TOKEN)


# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    username = request.data.get('username')
    password = request.data.get('password')
    email = request.data.get('email')
    bio = request.data.get('bio', '')
    profile_pic = request.FILES.get('profile_pic', None)

    if not username or not password or not email:
        return Response({"error": "Username, password and email are required"}, status=400)

    if User.objects.filter(username=username).exists():
        return Response({"error": "User already exists"}, status=400)

    if User.objects.filter(email=email).exists():
        return Response({"error": "Email already exists"}, status=400)

    user = User.objects.create_user(username=username, password=password, email=email)
    UserProfile.objects.create(user=user, bio=bio, profile_pic=profile_pic)

    return Response({'success': "User registered successfully"}, status=201)


@api_view(['POST'])
@permission_classes([AllowAny])
def login_user(request):
    username = request.data.get('username')
    password = request.data.get('password')

    if not username or not password:
        return Response({"error": "Username and password are required"}, status=400)

    user = authenticate(username=username, password=password)

    if user is not None:
        refresh = RefreshToken.for_user(user)
        return Response({
            "success": "Login successful",
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email
            }
        }, status=200)
    else:
        return Response({"error": "Invalid credentials"}, status=401)


# ─────────────────────────────────────────────
# GITHUB REPO FETCHING — parallel + cached
# ─────────────────────────────────────────────

CACHE_KEY = 'alu_repos_all'
CACHE_TIMEOUT = 60 * 30  # 30 minutes


def fetch_single_query(args):
    """Fetch all pages for a single search query. Runs in a thread."""
    query, headers, one_year_ago = args
    url = "https://api.github.com/search/repositories"
    results = []
    page = 1

    while page <= 5:  # reduced from 10 — beyond page 5 results are rarely relevant
        params = {
            "q": query,
            "sort": "updated",
            "order": "desc",
            "page": page,
            "per_page": 100
        }
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)

            # Respect GitHub rate limiting
            if response.status_code == 403:
                logger.warning(f"Rate limited on query: {query}")
                break

            if response.status_code != 200:
                break

            data = response.json()
            items = data.get('items', [])

            if not items:
                break

            for repo in items:
                pushed_at = repo.get('pushed_at', '')
                if pushed_at >= one_year_ago:
                    results.append(repo)

            # If the last item on this page is already older than 1 year, no point fetching more
            if items and items[-1].get('pushed_at', '') < one_year_ago:
                break

            page += 1

        except Exception as e:
            logger.error(f"Error fetching query '{query}': {e}")
            break

    return results


def fetch_all_alu_repos():
    """
    Fetch all ALU-related repos from GitHub using parallel requests.
    Returns a deduplicated, sorted list.
    """
    headers = {"Authorization": f"Bearer {settings.GITHUB_TOKEN}"}
    one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    search_queries = [
        f"alu- in:name pushed:>{one_year_ago}",
        f"alu_ in:name pushed:>{one_year_ago}",
        f"topic:alu pushed:>{one_year_ago}",
        f"topic:alx pushed:>{one_year_ago}",
        f"alu in:name pushed:>{one_year_ago}",
        f"alu in:description pushed:>{one_year_ago}",
        f"alu-zero_day in:name pushed:>{one_year_ago}",
        f"alu-scripting in:name pushed:>{one_year_ago}",
        f"alu-web in:name pushed:>{one_year_ago}",
        f"alu-backend in:name pushed:>{one_year_ago}",
        f"alu-devops in:name pushed:>{one_year_ago}",
        f"alu-infrastructure in:name pushed:>{one_year_ago}",
        f"alx- in:name pushed:>{one_year_ago}",
        f"alx_ in:name pushed:>{one_year_ago}",
    ]

    # Build args list to pass into each thread
    query_args = [(q, headers, one_year_ago) for q in search_queries]

    all_repos = []

    # Run all queries in parallel — max 5 threads to avoid hammering GitHub API
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = executor.map(fetch_single_query, query_args)
        for result in futures:
            all_repos.extend(result)

    # Deduplicate by full_name
    unique_repos = {}
    for repo in all_repos:
        full_name = repo.get('full_name')
        if not full_name:
            continue

        repo_name = repo.get('name', '').lower()

        # Filter: must actually be ALU-related
        is_alu = (
            repo_name.startswith('alu-') or
            repo_name.startswith('alu_') or
            repo_name.startswith('alx-') or
            repo_name.startswith('alx_') or
            'alu' in repo.get('topics', []) or
            'alx' in repo.get('topics', []) or
            'alu-zero_day' in repo_name or
            'alu-scripting' in repo_name or
            'alu-web' in repo_name or
            'alu-backend' in repo_name
        )

        if is_alu and full_name not in unique_repos:
            unique_repos[full_name] = repo

    final_repos = list(unique_repos.values())

    # Sort by most recently pushed, then stars
    final_repos.sort(
        key=lambda x: (x.get('pushed_at', ''), x.get('stargazers_count', 0)),
        reverse=True
    )

    return final_repos


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def alu_repos(request):
    """
    Returns paginated ALU repos.
    Results are cached for 30 minutes so GitHub is only hit once per cache window.

    Query params:
      ?page=1        (default: 1)
      ?per_page=20   (default: 20)
    """
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 20))

    # Try to get from cache first — avoids all GitHub API calls on subsequent requests
    all_repos = cache.get(CACHE_KEY)

    if all_repos is None:
        logger.info("Cache miss — fetching repos from GitHub (parallel)")
        all_repos = fetch_all_alu_repos()
        cache.set(CACHE_KEY, all_repos, timeout=CACHE_TIMEOUT)
        logger.info(f"Cached {len(all_repos)} repos for {CACHE_TIMEOUT // 60} minutes")
    else:
        logger.info(f"Cache hit — serving {len(all_repos)} repos from cache")

    total = len(all_repos)
    start = (page - 1) * per_page
    end = start + per_page
    page_repos = all_repos[start:end]

    return Response({
        'success': True,
        'total_count': total,
        'page': page,
        'per_page': per_page,
        'has_more': end < total,
        'items': page_repos,
        'filter': {
            'since': (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"),
            'message': 'Repositories updated in the last year'
        }
    })


# ─────────────────────────────────────────────
# IMPORT
# ─────────────────────────────────────────────

from services.import_service import GitHubImportService, RepoCustomizer


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_repository(request):
    try:
        user = request.user

        if not hasattr(user, 'profile'):
            return Response({
                'success': False,
                'error': 'User profile not found. Please complete your profile.'
            }, status=400)

        user_profile = user.profile

        if not user_profile.github_token:
            return Response({
                'success': False,
                'error': 'GitHub account not connected. Please connect your GitHub account first.'
            }, status=400)

        github_token = user_profile.github_token
        owner = request.data.get('owner')
        repo = request.data.get('repo')
        new_name = request.data.get('new_name', repo)
        rename_project = request.data.get('rename_project', False)
        add_attribution = request.data.get('add_attribution', True)

        if not owner or not repo:
            return Response({
                'success': False,
                'error': 'Owner and repo name are required'
            }, status=400)

        import_service = GitHubImportService(github_token)

        logger.info(f"Forking {owner}/{repo} for user {user.username}")
        fork_result = import_service.fork_repository(owner, repo)

        if not fork_result:
            return Response({
                'success': False,
                'error': 'Failed to fork repository. It might already exist or you may not have permission.'
            }, status=500)

        forked_repo = fork_result
        forked_owner = forked_repo.get('owner', {}).get('login', user.username)
        forked_repo_name = forked_repo.get('name', repo)

        if new_name != repo:
            logger.info(f"Renaming {forked_repo_name} to {new_name}")
            rename_url = f"https://api.github.com/repos/{forked_owner}/{forked_repo_name}"
            response = requests.patch(
                rename_url,
                headers=import_service.headers,
                json={'name': new_name}
            )
            if response.status_code == 200:
                forked_repo_name = new_name
            else:
                logger.warning(f"Failed to rename repo: {response.status_code}")

        customizer = RepoCustomizer(import_service, forked_owner, forked_repo_name)
        customizations = []

        if rename_project:
            changes = customizer.rename_project(repo, new_name)
            customizations.extend(changes)

        if add_attribution:
            original_url = f"https://github.com/{owner}/{repo}"
            if customizer.add_import_note(original_url):
                customizations.append('attribution_note')

        from .models import ImportHistory
        import_record = ImportHistory.objects.create(
            user=user,
            original_owner=owner,
            original_repo=repo,
            imported_repo_name=forked_repo_name,
            imported_repo_url=f"https://github.com/{forked_owner}/{forked_repo_name}",
            customizations_applied=customizations,
            status='success'
        )

        return Response({
            'success': True,
            'message': f'Successfully imported {repo} to your GitHub account',
            'imported_repo': {
                'name': forked_repo_name,
                'url': f"https://github.com/{forked_owner}/{forked_repo_name}",
                'owner': forked_owner
            },
            'customizations': customizations,
            'import_id': import_record.id
        }, status=200)

    except Exception as e:
        logger.error(f"Import error: {e}")
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def import_status(request, import_id):
    from .models import ImportHistory
    try:
        import_record = ImportHistory.objects.get(id=import_id, user=request.user)
        return Response({
            'success': True,
            'status': import_record.status,
            'imported_repo_url': import_record.imported_repo_url,
            'created_at': import_record.created_at
        }, status=status.HTTP_200_OK)
    except ImportHistory.DoesNotExist:
        return Response({'success': False, 'error': 'Import record not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_imports(request):
    from .models import ImportHistory
    imports = ImportHistory.objects.filter(user=request.user).order_by('-created_at')
    data = [{
        'id': imp.id,
        'original_repo': f"{imp.original_owner}/{imp.original_repo}",
        'imported_repo_name': imp.imported_repo_name,
        'imported_repo_url': imp.imported_repo_url,
        'customizations': imp.customizations_applied,
        'status': imp.status,
        'created_at': imp.created_at
    } for imp in imports]

    return Response({'success': True, 'imports': data}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def connect_github(request):
    github_token = request.data.get('github_token')

    if not github_token:
        return Response({'error': 'GitHub token is required'}, status=400)

    headers = {'Authorization': f'token {github_token}'}
    response = requests.get('https://api.github.com/user', headers=headers)

    if response.status_code != 200:
        return Response({'error': 'Invalid GitHub token'}, status=400)

    user_data = response.json()
    profile = request.user.profile
    profile.github_token = github_token
    profile.github_username = user_data.get('login')
    profile.save()

    return Response({
        'success': True,
        'message': 'GitHub account connected successfully',
        'username': user_data.get('login')
    })