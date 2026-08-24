<div align="center">

# 🚽 급똥

### 급할 때, 내 주변 공중화장실을 가장 빠르게 찾는 지도 서비스

[![서비스 열기](https://img.shields.io/badge/서비스%20열기-geupddong.com-17683A?style=for-the-badge)](https://geupddong.com)
[![API 상태](https://img.shields.io/badge/API%20Health-확인하기-2E7D4F?style=for-the-badge)](https://api.geupddong.com/api/health)

</div>

## 💡 급똥이란?

급똥은 공공데이터와 카카오맵을 활용해, 현재 위치 또는 검색한 장소 주변의 공중화장실을 빠르게 찾을 수 있는 서비스입니다.
지도 위의 화장실 정보를 한눈에 보고, 필요한 상세 정보까지 바로 확인할 수 있도록 만들었습니다.

| 🌐 서비스 | 🔌 Public API | 🔒 운영 환경 |
| --- | --- | --- |
| [geupddong.com](https://geupddong.com) | [api.geupddong.com](https://api.geupddong.com) | Cloudflare HTTPS · Mini PC Docker |

## 🗂️ 저장소 구성

| 구분 | 저장소 | 역할 |
| --- | --- | --- |
| 🗺️ Web | [toilet-web](https://github.com/toilet-project/toilet-web) | React·Vite 기반 지도 웹 클라이언트 |
| 🔌 API | [toilet-api](https://github.com/toilet-project/toilet-api) | 지도 영역·화장실 상세 조회 REST API |
| 🔄 Batch | [toilet-batch](https://github.com/toilet-project/toilet-batch) | 공공데이터 수집·정제·DB 반영 |
| 🛠️ Admin | [toilet-admin-api](https://github.com/toilet-project/toilet-admin-api) | 데이터 관리용 관리자 API |
| 📚 Docs | [docs](https://github.com/toilet-project/docs) | 명세, 아키텍처, 운영 가이드, WBS |

## ✨ 주요 기능

| 기능 | 설명 |
| --- | --- |
| 📍 현재 위치 기반 조회 | GPS 권한을 받아 내 주변 화장실을 지도에 표시합니다. |
| 🔎 장소 검색 | 카카오 장소 검색 자동완성으로 원하는 위치로 지도를 이동합니다. |
| 🧩 줌 레벨 클러스터링 | 지도 축척에 따라 마커·클러스터를 조정해 복잡도를 낮춥니다. |
| 🚻 상세 정보 카드 | 주소, 개방시간, 설치연월, 편의·안전시설, 거리 정보를 제공합니다. |
| 📋 주소 복사·시설 위치 | 주소를 복사하고 비상벨·CCTV·기저귀 교환대 위치를 확인합니다. |
| 🔄 데이터 갱신 | 배치 서버가 공공데이터를 수집·정제해 운영 DB를 갱신합니다. |

## 🏗️ 아키텍처

<p align="center">
  <img src="architecture-v2.svg" alt="급똥 아키텍처 v2" width="100%" />
</p>

```text
사용자 → Cloudflare HTTPS → geupddong.com (React + Vite)
                          └→ api.geupddong.com → Nginx → API / Batch / Admin / MySQL
```

- 외부 요청은 Cloudflare와 Nginx를 거쳐 HTTPS로 처리합니다.
- 서버는 Mini PC Docker Compose에서 구동되며, API·Batch·Admin은 MySQL을 공유합니다.
- GitHub Actions가 Docker Hub 이미지 빌드 후 SSH 배포를 수행합니다.

## 📖 더 알아보기

| 문서 | 내용 |
| --- | --- |
| [아키텍처 v2](architecture-v2.md) | 구성 요소, 데이터 흐름, 외부 공개 원칙 |
| [운영 가이드](operations.md) | 도메인, HTTPS, 배포 및 비밀정보 관리 |
| [API 명세](api_spec.md) | 지도 영역 조회와 화장실 상세 조회 |
| [DB 테이블 명세](db_table.md) | 화장실 데이터베이스 구조 |
| [요구사항 정의서](requirements.md) | 서비스 목표와 향후 확장 범위 |
| [WBS](https://github.com/orgs/toilet-project/projects/2/views/2) | 프로젝트 일정과 작업 현황 |

---

<div align="center">
  <sub>공공데이터 기반 공중화장실 지도 서비스 · 급똥</sub>
</div>
