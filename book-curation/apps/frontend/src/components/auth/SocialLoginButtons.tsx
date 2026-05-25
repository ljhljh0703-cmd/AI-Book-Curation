import { useEffect, useMemo, useState } from "react";
import GoogleLoginButton from "./GoogleLoginButton";
import KakaoLoginButton from "./KakaoLoginButton";
import { getOAuthProviders } from "@/api/authApi";
import type { OAuth2ProviderItem } from "@/types/auth";

type Props = {
  disabled?: boolean;
};

const SocialLoginButtons = ({ disabled = false }: Props) => {
  const [providers, setProviders] = useState<OAuth2ProviderItem[]>([]);

  useEffect(() => {
    let active = true;

    const loadProviders = async () => {
      try {
        // 수정: 백엔드에 실제 등록된 OAuth provider만 받아와 버튼을 렌더링합니다.
        const response = await getOAuthProviders();
        if (!active) return;
        setProviders(response.providers ?? []);
      } catch {
        if (!active) return;
        setProviders([]);
      }
    };

    void loadProviders();

    return () => {
      active = false;
    };
  }, []);

  const providerMap = useMemo(() => {
    return new Map(
      providers.map((provider) => [provider.provider, provider.authorizationUrl])
    );
  }, [providers]);

  const moveToAuthorizationUrl = (authorizationUrl?: string) => {
    if (!authorizationUrl) return;

    // 수정: 백엔드가 내려준 authorizationUrl을 그대로 사용합니다.
    window.location.assign(authorizationUrl);
  };

  if (providers.length === 0) {
    return null;
  }

  return (
    <div className="flex w-full flex-col gap-2">
      {providerMap.has("GOOGLE") && (
        <div className="w-full">
          <GoogleLoginButton
            onClick={() => moveToAuthorizationUrl(providerMap.get("GOOGLE"))}
            disabled={disabled}
          />
        </div>
      )}

      {providerMap.has("KAKAO") && (
        <div className="w-full">
          <KakaoLoginButton
            onClick={() => moveToAuthorizationUrl(providerMap.get("KAKAO"))}
            disabled={disabled}
          />
        </div>
      )}
    </div>
  );
};

export default SocialLoginButtons;
