/**
 * 마이페이지 화면.
 * 계정 정보, 독서 프로필, 나만의 도서관, 독서대를 관리한다.
 */

import {
  BookOpen,
  Building2,
  ChevronRight,
  CircleHelp,
  Edit3,
  Home,
  Link2,
  LogOut,
  Mail,
  Pencil,
  Save,
  Sparkles,
  UserRound,
  UserX,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  getMe,
  getOAuthProviders,
  logout,
  startSocialLink,
  unlinkSocialLink,
  updateNickname,
  withdraw,
} from "../api/authApi";
import {
  getMyCharacter,
  getMyProfile,
  updateMyCharacterNickname,
  type BookShelfReviewResponse,
  type CharacterLevelUpEvent,
  type UserCharacterResponse,
  type UserProfileResponse,
} from "../api/userProfileApi";
import ProfileInfoRow from "../components/profile/ProfileInfoRow";
import UserPreferredLibrariesPanel from "../components/profile/UserPreferredLibrariesPanel";
import CharacterLevelUpModal from "../components/profile/CharacterLevelUpModal";
import UserBookstandPanel from "../components/profile/UserBookstandPanel";
import UserProfileViewCard from "../components/profile/UserProfileViewCard";
import type { MeResponse, Provider } from "../types/auth";
import { toCacheBustedImageUrl } from "../utils/imageUrl";
import { clearUser, saveUser } from "../utils/storage";


const getErrorMessage = (error: unknown) => {
  if (error instanceof Error && error.message) return error.message;
  return "사용자 정보를 불러오지 못했습니다.";
};

const PROVIDER_LABELS: Record<string, string> = {
  GOOGLE: "Google",
  KAKAO: "Kakao",
  NAVER: "Naver",
};

type ProfileMenu = "profile" | "libraries" | "bookstand";

const ProfilePage = () => {
  const navigate = useNavigate();
  const [user, setUser] = useState<MeResponse | null>(null);
  const [profile, setProfile] = useState<UserProfileResponse | null>(null);
  const [character, setCharacter] = useState<UserCharacterResponse | null>(null);
  const [availableProviders, setAvailableProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(true);
  const [logoutLoading, setLogoutLoading] = useState(false);
  const [withdrawLoading, setWithdrawLoading] = useState(false);
  const [activeMenu, setActiveMenu] = useState<ProfileMenu>("profile");
  const [linkLoadingProvider, setLinkLoadingProvider] = useState<Provider | null>(null);
  const [unlinkLoadingProvider, setUnlinkLoadingProvider] = useState<Provider | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [nicknameEditMode, setNicknameEditMode] = useState(false);
  const [nicknameInput, setNicknameInput] = useState("");
  const [nicknameSaving, setNicknameSaving] = useState(false);
  const [characterNicknameInput, setCharacterNicknameInput] = useState("");
  const [characterNicknameEditMode, setCharacterNicknameEditMode] = useState(false);
  const [characterNicknameSaving, setCharacterNicknameSaving] = useState(false);
  const [characterNicknameMessage, setCharacterNicknameMessage] = useState("");
  const [levelUpEvent, setLevelUpEvent] = useState<CharacterLevelUpEvent | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [me, myProfile, myCharacter] = await Promise.all([
          getMe(),
          getMyProfile(),
          getMyCharacter(),
        ]);

        setUser(me);
        setNicknameInput(me.nickname);
        setProfile(myProfile);
        setCharacter(myCharacter);
        setCharacterNicknameInput(myCharacter.characterNickname || "북케몬 알");
        saveUser(me);

        try {
          const providerResponse = await getOAuthProviders();
          setAvailableProviders(
            providerResponse.providers.map((item) => item.provider)
          );
        } catch {
          setAvailableProviders([]);
        }
      } catch (error) {
        clearUser();
        setErrorMessage(getErrorMessage(error));
      } finally {
        setLoading(false);
      }
    };

    void fetchData();
  }, []);

  const linkedProviders = useMemo(
    () => new Set(user?.linkedProviders ?? []),
    [user]
  );

  const characterExpPercent = useMemo(
    () => character?.experiencePercent ?? 0,
    [character]
  );

  const refreshCharacter = async () => {
    try {
      const updatedCharacter = await getMyCharacter();
      setCharacter(updatedCharacter);
      setCharacterNicknameInput(updatedCharacter.characterNickname || "북케몬 알");
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  };

  const handleBookReviewSaved = async (response: BookShelfReviewResponse) => {
    // 수정 포인트: 리뷰 완료 응답에 포함된 캐릭터 정보를 우선 사용해 레벨/이미지를 즉시 갱신합니다.
    if (response.character) {
      setCharacter(response.character);
      setCharacterNicknameInput(response.character.characterNickname || "북케몬 알");
    } else {
      await refreshCharacter();
    }

    if (response.levelUpEvent) {
      setLevelUpEvent(response.levelUpEvent);
    }
  };

  const handleLogout = async () => {
    setLogoutLoading(true);

    try {
      await logout();
    } finally {
      clearUser();
      setLogoutLoading(false);
      navigate("/login", { replace: true });
    }
  };

  const handleWithdraw = async () => {
    if (!window.confirm("정말 회원탈퇴 하시겠습니까? 탈퇴 후에는 다시 로그인할 수 없습니다.")) {
      return;
    }

    setErrorMessage("");
    setWithdrawLoading(true);

    try {
      const response = await withdraw();
      clearUser();
      navigate("/login", {
        replace: true,
        state: { message: response.message },
      });
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setWithdrawLoading(false);
    }
  };

  const handleSaveSuccess = (updatedProfile: UserProfileResponse) => {
    setProfile(updatedProfile);
  };

  const handleNicknameSave = async () => {
    const nickname = nicknameInput.trim();
    if (nickname.length < 2 || nickname.length > 30) {
      setErrorMessage("닉네임은 2자 이상 30자 이하로 입력해 주세요.");
      return;
    }

    setErrorMessage("");
    setNicknameSaving(true);

    try {
      const updatedUser = await updateNickname({ nickname });
      setUser(updatedUser);
      saveUser(updatedUser);
      setNicknameEditMode(false);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setNicknameSaving(false);
    }
  };

  const handleCharacterNicknameAction = async () => {
    if (!characterNicknameEditMode) {
      setCharacterNicknameInput(character?.characterNickname || "북케몬");
      setCharacterNicknameMessage("");
      setCharacterNicknameEditMode(true);
      return;
    }

    const characterNickname = characterNicknameInput.trim();
    if (characterNickname.length < 1 || characterNickname.length > 30) {
      setErrorMessage("캐릭터 닉네임은 1자 이상 30자 이하로 입력해 주세요.");
      return;
    }

    setErrorMessage("");
    setCharacterNicknameMessage("");
    setCharacterNicknameSaving(true);

    try {
      const updatedCharacter = await updateMyCharacterNickname({ characterNickname });
      setCharacter(updatedCharacter);
      setCharacterNicknameInput(updatedCharacter.characterNickname || "북케몬");
      setCharacterNicknameEditMode(false);
      setCharacterNicknameMessage("캐릭터명이 수정되었습니다.");
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setCharacterNicknameSaving(false);
    }
  };

  const handleStartSocialLink = async (provider: Provider) => {
    setErrorMessage("");
    setLinkLoadingProvider(provider);

    try {
      const response = await startSocialLink(provider);
      window.location.assign(response.authorizationUrl);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
      setLinkLoadingProvider(null);
    }
  };

  const handleUnlinkSocialLink = async (provider: Provider) => {
    const providerLabel = PROVIDER_LABELS[provider] ?? provider;
    if (!window.confirm(`${providerLabel} 소셜 로그인 연동을 해제하시겠습니까?`)) {
      return;
    }

    setErrorMessage("");
    setUnlinkLoadingProvider(provider);

    try {
      const updatedUser = await unlinkSocialLink(provider);
      setUser(updatedUser);
      saveUser(updatedUser);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setUnlinkLoadingProvider(null);
    }
  };

  const menuButtonClass = (menu: ProfileMenu) =>
    cn(
      "group flex w-full items-center justify-between rounded-2xl px-4 py-3 text-left text-sm font-semibold transition-all",
      activeMenu === menu
        ? "bg-slate-950 text-white shadow-lg shadow-slate-900/10"
        : "text-slate-500 hover:bg-white hover:text-slate-950 hover:shadow-sm"
    );

  return (
    <main className="min-h-[calc(100vh-4rem)] bg-slate-50 px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto grid w-full max-w-7xl gap-6 lg:grid-cols-[280px_1fr]">
        <aside className="h-fit rounded-[2rem] border border-slate-200/80 bg-white p-4 shadow-xl shadow-slate-200/60">
          <div className="relative rounded-3xl bg-gradient-to-br from-slate-950 via-indigo-950 to-violet-800 p-5 text-white">
            {/* 수정 포인트: 부모 overflow-hidden 때문에 tooltip이 잘리던 문제를 막기 위해 장식 배경만 별도 overflow-hidden 레이어로 분리합니다. */}
            <div className="pointer-events-none absolute inset-0 overflow-hidden rounded-3xl">
              <div className="absolute -right-8 -top-8 size-32 rounded-full bg-violet-400/30 blur-2xl" />
              <div className="absolute -bottom-10 -left-10 size-36 rounded-full bg-indigo-400/20 blur-3xl" />
            </div>

            <div className="relative flex flex-col items-center text-center">
              <div className="inline-flex items-center gap-1 rounded-full bg-white/12 px-3 py-1 text-[11px] font-semibold text-violet-100 ring-1 ring-white/15">
                <Sparkles className="size-3" /> 나의 북케몬
              </div>

              <div className="mt-4 flex size-28 items-center justify-center rounded-[2rem] bg-white/95 shadow-2xl shadow-black/20 ring-1 ring-white/50">
                {character?.currentImageUrl ? (
                  <img
                    src={toCacheBustedImageUrl(character.currentImageUrl, character.reviewGrowthCount)}
                    alt="북케몬 캐릭터"
                    className="size-20 rounded-3xl object-contain"
                  />
                ) : (
                  <Sparkles className="size-12 text-violet-600" />
                )}
              </div>

              <div className="mt-4 w-full rounded-3xl bg-white/10 p-4 text-left ring-1 ring-white/15">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold text-violet-100">
                      Lv.{character?.characterLevel ?? 1} 경험치
                    </p>
                    <p className="mt-1 text-[11px] text-white/70">
                      {character && character.characterLevel >= character.maxLevel
                        ? "최대 레벨에 도달했습니다."
                        : "다음 성장 단계까지 진행도"}
                    </p>
                  </div>
                  <div className="relative group">
                    <button
                      type="button"
                      className="inline-flex size-7 items-center justify-center rounded-full bg-white/12 text-violet-100 ring-1 ring-white/15 transition hover:bg-white/20"
                      aria-label="경험치 가이드"
                    >
                      <CircleHelp className="size-4" />
                    </button>
                    {/* 수정 포인트: tooltip이 카드 영역을 벗어나도 잘리지 않도록 z-index와 부모 overflow 구조를 조정했습니다. */}
                    <div className="pointer-events-none absolute right-0 top-9 z-50 hidden w-64 max-w-[calc(100vw-2rem)] rounded-2xl bg-slate-950/95 px-3 py-2 text-[11px] leading-5 text-white shadow-2xl ring-1 ring-white/10 group-hover:block">
                      처음 지급되는 캐릭터는 Lv.1입니다. 첫 리뷰 완료 시 Lv.2가 되고, Lv.2는 리뷰당 20, Lv.3은 리뷰당 10 경험치가 쌓입니다.
                    </div>
                  </div>
                </div>

                <div
                  className="mt-3 h-3 overflow-hidden rounded-full bg-white/15"
                  title={`현재 경험치 ${characterExpPercent}%`}
                  aria-label={`현재 경험치 ${characterExpPercent}%`}
                >
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-emerald-300 via-sky-300 to-violet-300 transition-all duration-300"
                    style={{ width: `${characterExpPercent}%` }}
                  />
                </div>
                <div className="mt-2 flex items-center justify-between text-[11px] text-white/70">
                  <span>
                    현재 경험치 {character?.experience ?? 0}/{character?.experienceToNextLevel ?? 100}
                  </span>
                  <span>{characterExpPercent}%</span>
                </div>
              </div>

              <div className="mt-4 w-full rounded-3xl bg-white/10 p-3 text-left ring-1 ring-white/15">
                <label
                  htmlFor="characterNickname"
                  className="mb-2 flex items-center gap-2 text-xs font-semibold text-violet-100"
                >
                  <Edit3 className="size-3.5" /> 캐릭터 닉네임
                </label>
                <div className="flex gap-2">
                  <Input
                    id="characterNickname"
                    value={characterNicknameInput}
                    onChange={(event) => setCharacterNicknameInput(event.target.value)}
                    placeholder="캐릭터명"
                    className="h-10 rounded-2xl border-white/15 bg-white/95 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-80"
                    maxLength={30}
                    disabled={!characterNicknameEditMode || characterNicknameSaving}
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    className="h-10 shrink-0 rounded-2xl bg-white/90 px-3 text-xs font-bold text-slate-950 hover:bg-white"
                    onClick={handleCharacterNicknameAction}
                    disabled={characterNicknameSaving || !character}
                    aria-label={characterNicknameEditMode ? "캐릭터명 확인" : "캐릭터명 수정"}
                  >
                    {characterNicknameEditMode ? (
                      <>
                        <Save className="size-3.5" /> 확인
                      </>
                    ) : (
                      <>
                        <Pencil className="size-3.5" /> 수정
                      </>
                    )}
                  </Button>
                </div>
                {characterNicknameMessage && (
                  <p className="mt-2 text-xs font-semibold text-emerald-100">
                    {characterNicknameMessage}
                  </p>
                )}
              </div>
            </div>
          </div>

          <nav className="mt-4 space-y-2">
            <button
              type="button"
              className={menuButtonClass("profile")}
              onClick={() => setActiveMenu("profile")}
            >
              <span className="flex items-center gap-3">
                <UserRound className="size-4" />
                정보수정
              </span>
              <ChevronRight className="size-4 opacity-50 transition-transform group-hover:translate-x-0.5" />
            </button>
            <button
              type="button"
              className={menuButtonClass("libraries")}
              onClick={() => setActiveMenu("libraries")}
            >
              <span className="flex items-center gap-3">
                <Building2 className="size-4" />
                나만의 도서관
              </span>
              <ChevronRight className="size-4 opacity-50 transition-transform group-hover:translate-x-0.5" />
            </button>
            <button
              type="button"
              className={menuButtonClass("bookstand")}
              onClick={() => setActiveMenu("bookstand")}
            >
              <span className="flex items-center gap-3">
                <BookOpen className="size-4" />
                독서대
              </span>
              <ChevronRight className="size-4 opacity-50 transition-transform group-hover:translate-x-0.5" />
            </button>
          </nav>

          <div className="mt-5 space-y-1 border-t border-slate-100 pt-4">
            <Button
              variant="ghost"
              className="w-full justify-start rounded-2xl"
              onClick={() => navigate("/")}
            >
              <Home className="size-4" />
              홈으로
            </Button>
            <Button
              variant="ghost"
              className="w-full justify-start rounded-2xl"
              onClick={handleLogout}
              disabled={logoutLoading}
            >
              <LogOut className="size-4" />
              {logoutLoading ? "처리 중..." : "로그아웃"}
            </Button>
            <Button
              variant="ghost"
              className="w-full justify-start rounded-2xl text-destructive hover:text-destructive"
              onClick={handleWithdraw}
              disabled={withdrawLoading || loading || !user}
            >
              <UserX className="size-4" />
              {withdrawLoading ? "탈퇴 처리 중..." : "회원탈퇴"}
            </Button>
          </div>
        </aside>

        <section className="min-w-0 space-y-6">
          <div className="rounded-[2rem] border border-slate-200/80 bg-white p-6 shadow-xl shadow-slate-200/60 sm:p-8">
            <p className="text-sm font-medium text-primary">Bookemon account</p>
            <h2 className="mt-2 text-3xl font-bold tracking-tight text-slate-950">
              마이페이지
            </h2>
          </div>

          {loading && (
            <Card className="rounded-[2rem] border-slate-200/80 shadow-xl shadow-slate-200/60">
              <CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-muted-foreground">
                <div className="size-10 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                <span className="text-sm">사용자 정보를 불러오는 중...</span>
              </CardContent>
            </Card>
          )}

          {errorMessage && <Alert variant="destructive">{errorMessage}</Alert>}

          {!loading && !errorMessage && activeMenu === "profile" && user && (
            <>
              <Card className="rounded-[2rem] border-slate-200/80 shadow-xl shadow-slate-200/60">
                <CardHeader className="gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="space-y-1">
                    <CardDescription>계정 정보</CardDescription>
                    <CardTitle className="text-2xl">내 정보</CardTitle>
                  </div>

                  {availableProviders.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {availableProviders.map((provider) => {
                        const linked = linkedProviders.has(provider);
                        const loadingCurrent = linkLoadingProvider === provider;
                        const unlinkingCurrent = unlinkLoadingProvider === provider;

                        return (
                          <div
                            key={provider}
                            className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white p-1"
                          >
                            <Button
                              type="button"
                              size="sm"
                              variant={linked ? "secondary" : "outline"}
                              className="rounded-full px-3 text-xs"
                              disabled={linked || loadingCurrent || unlinkingCurrent}
                              onClick={() => handleStartSocialLink(provider)}
                              title={`${PROVIDER_LABELS[provider] ?? provider} ${linked ? "연동됨" : "연동"}`}
                            >
                              <Link2 className="size-3.5" />
                              {PROVIDER_LABELS[provider] ?? provider}
                              <span className="text-[11px] text-muted-foreground">
                                {linked ? "연동됨" : loadingCurrent ? "이동 중" : "연동"}
                              </span>
                            </Button>
                            {linked && (
                              <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                className="h-8 rounded-full px-2 text-xs text-destructive hover:text-destructive"
                                disabled={unlinkingCurrent}
                                onClick={() => handleUnlinkSocialLink(provider)}
                                title={`${PROVIDER_LABELS[provider] ?? provider} 연동 해제`}
                              >
                                {unlinkingCurrent ? "해제 중" : "해제"}
                              </Button>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="grid gap-4 md:grid-cols-2">
                    <ProfileInfoRow
                      label="이메일"
                      value={
                        <span className="inline-flex items-center gap-2">
                          <Mail className="size-4 text-slate-400" />
                          {user.email ?? "미입력"}
                        </span>
                      }
                    />
                    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                          닉네임
                        </span>
                        {!nicknameEditMode && (
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            className="h-8 rounded-xl"
                            onClick={() => setNicknameEditMode(true)}
                          >
                            <Pencil className="size-3.5" /> 수정
                          </Button>
                        )}
                      </div>

                      {!nicknameEditMode ? (
                        <div className="mt-3 min-h-7 break-all text-base font-bold text-slate-950">
                          {user.nickname}
                        </div>
                      ) : (
                        <div className="mt-3 flex gap-2">
                          <Input
                            value={nicknameInput}
                            onChange={(event) => setNicknameInput(event.target.value)}
                            maxLength={30}
                            className="rounded-xl"
                          />
                          <Button
                            type="button"
                            size="sm"
                            className="rounded-xl"
                            onClick={handleNicknameSave}
                            disabled={nicknameSaving}
                          >
                            <Save className="size-4" />
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            className="rounded-xl"
                            onClick={() => {
                              setNicknameInput(user.nickname);
                              setNicknameEditMode(false);
                            }}
                          >
                            <X className="size-4" />
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>

              {profile?.onboardingCompleted && (
                <Card className="rounded-[2rem] border-slate-200/80 shadow-xl shadow-slate-200/60">
                  <CardHeader>
                    <div className="space-y-1">
                      <CardTitle className="text-2xl">독서 프로필</CardTitle>
                      <p className="text-sm leading-6 text-muted-foreground">
                        독서 프로필은 개인화 맞춤 추천 품질을 높이기 위해 활용됩니다.
                      </p>
                    </div>
                  </CardHeader>

                  <CardContent>
                    <UserProfileViewCard
                      profile={profile}
                      onSaveSuccess={handleSaveSuccess}
                    />
                  </CardContent>
                </Card>
              )}

              {profile && !profile.onboardingCompleted && (
                <Card className="rounded-[2rem] border-dashed border-primary/30 bg-primary/5 shadow-xl shadow-slate-200/40">
                  <CardHeader>
                    <CardDescription>온보딩 미완료</CardDescription>
                    <CardTitle className="text-2xl">독서 프로필을 아직 만들지 않았어요</CardTitle>
                    <p className="text-sm leading-6 text-muted-foreground">
                      온보딩을 건너뛴 회원은 독서 프로필 정보가 표시되지 않습니다.
                      다시 로그인하거나 아래 버튼을 누르면 온보딩을 진행할 수 있고, 완료 후 이 영역에서 취향 정보를 확인할 수 있습니다.
                    </p>
                  </CardHeader>
                  <CardContent>
                    <Button type="button" className="rounded-2xl" onClick={() => navigate("/onboarding")}>
                      온보딩 진행하기
                    </Button>
                  </CardContent>
                </Card>
              )}
            </>
          )}

          {!loading && !errorMessage && activeMenu === "libraries" && (
            <Card className="rounded-[2rem] border-slate-200/80 shadow-xl shadow-slate-200/60">
              <CardHeader>
                <CardDescription>도서관 추천 기준</CardDescription>
                <CardTitle className="text-2xl">나만의 도서관</CardTitle>
              </CardHeader>
              <CardContent>
                <UserPreferredLibrariesPanel profile={profile} />
              </CardContent>
            </Card>
          )}

          {!loading && !errorMessage && activeMenu === "bookstand" && (
            <Card className="rounded-[2rem] border-slate-200/80 shadow-xl shadow-slate-200/60">
              <CardHeader>
                <CardDescription>독서 기록</CardDescription>
                <CardTitle className="text-2xl">독서대</CardTitle>
                <p className="text-sm leading-6 text-muted-foreground">
                  읽는 중인 책, 읽은 책, 관심있는 책, 관심없는 책을 분리해서 관리합니다.
                </p>
              </CardHeader>
              <CardContent>
                <UserBookstandPanel onReviewSaved={handleBookReviewSaved} />
              </CardContent>
            </Card>
          )}
        </section>
      </div>

      {levelUpEvent && (
        <CharacterLevelUpModal
          event={levelUpEvent}
          onClose={() => setLevelUpEvent(null)}
        />
      )}
    </main>
  );
};

export default ProfilePage;