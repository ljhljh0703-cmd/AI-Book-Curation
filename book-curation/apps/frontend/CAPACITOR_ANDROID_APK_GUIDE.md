# Bookemon Android APK 빌드 가이드

이 패치는 기존 React/Vite 프론트엔드에 Capacitor Android 패키징 설정을 추가합니다.

## 반영된 내용

- `capacitor.config.ts` 추가
- `package.json`에 Capacitor 의존성과 스크립트 추가
- `.env.mobile` 추가
- Capacitor 앱 실행 시 `/api`, `/oauth2`, `/uploads` 상대경로가 `capacitor://localhost`로 붙지 않도록 `https://book.taeo-dev.com` 기준으로 보정
- Android WebView용 safe-area, 터치 하이라이트, input zoom 방지 CSS 보정
- 앱 실행 시 React Router를 `HashRouter`로 전환해서 새로고침/내부 라우팅 문제 완화

## 최초 1회 설치

```bash
cd apps/frontend
npm install
```

> 이번 패치는 `package.json`에 Capacitor 의존성을 추가합니다. 기존 `package-lock.json`과 맞추려면 반드시 `npm install`을 먼저 실행해 주세요. 그 다음부터는 `npm ci`를 사용해도 됩니다.

## Android 프로젝트 생성

최초 1회만 실행합니다.

```bash
cd apps/frontend
npm run build:mobile
npm run cap:add:android
```

위 명령이 성공하면 `apps/frontend/android` 폴더가 생성됩니다.

## React 수정 사항을 Android 앱에 반영

프론트 소스를 수정한 뒤 APK를 다시 만들 때마다 실행합니다.

```bash
cd apps/frontend
npm run cap:sync:android
```

## Android Studio 열기

```bash
cd apps/frontend
npm run cap:open:android
```

Android Studio가 열리면 Gradle Sync가 끝날 때까지 기다립니다.

## Debug APK 만들기

### Android Studio에서 빌드

1. 상단 메뉴에서 `Build` 선택
2. `Build Bundle(s) / APK(s)` 선택
3. `Build APK(s)` 선택
4. 빌드 완료 후 `locate` 클릭

보통 APK 위치는 다음 중 하나입니다.

```text
apps/frontend/android/app/build/outputs/apk/debug/app-debug.apk
```

### 터미널에서 빌드

Windows Git Bash 또는 macOS/Linux:

```bash
cd apps/frontend/android
./gradlew assembleDebug
```

Windows CMD/PowerShell:

```bat
cd apps\frontend\android
gradlew.bat assembleDebug
```

## 팀원에게 전달할 파일

Debug APK 기준:

```text
apps/frontend/android/app/build/outputs/apk/debug/app-debug.apk
```

팀원 Android 폰에서는 APK 설치 시 `알 수 없는 앱 설치 허용`이 필요할 수 있습니다.

## Release APK 참고

스토어가 아니라 팀원 테스트용이면 debug APK로 충분합니다. 다만 더 배포용에 가깝게 만들려면 keystore를 만든 뒤 release signing 설정을 해야 합니다.

```bash
cd apps/frontend/android
./gradlew assembleRelease
```

Release APK는 서명 설정이 없으면 설치 가능한 APK가 나오지 않을 수 있습니다. 처음 테스트는 `assembleDebug`를 권장합니다.

## 주의사항

- 앱 빌드는 `.env.mobile`을 사용합니다.
- 앱 안에서 API는 `https://book.taeo-dev.com/api`로 호출합니다.
- 소셜 로그인은 Android WebView에서 쿠키/리다이렉트가 브라우저와 다를 수 있으니 APK 설치 후 가장 먼저 테스트해 주세요.
- 앱 아이콘/스플래시는 Android 프로젝트 생성 후 별도 커스터마이징하면 됩니다.
