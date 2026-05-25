const isValidCalendarDate = (year: number, month: number, day: number) => {
  const date = new Date(year, month - 1, day);

  return (
    date.getFullYear() === year &&
    date.getMonth() === month - 1 &&
    date.getDate() === day
  );
};

const isValidBirthDate = (birthDate: string) => {
  if (!/^\d{6}$/.test(birthDate)) {
    return false;
  }

  const year = Number(birthDate.slice(0, 2));
  const month = Number(birthDate.slice(2, 4));
  const day = Number(birthDate.slice(4, 6));

  // 수정 포인트: 성별코드가 아직 입력되지 않은 상태에서도 99/00년대 생년월일을 자연스럽게 검증합니다.
  return (
    isValidCalendarDate(1900 + year, month, day) ||
    isValidCalendarDate(2000 + year, month, day)
  );
};

export const getResidentProfileValidationMessage = (
  birthDate: string,
  genderCode: string
): string => {
  if (!birthDate && !genderCode) {
    return "생년월일 6자리와 성별코드 1~4 중 하나를 입력해주세요.";
  }

  if (!/^\d{6}$/.test(birthDate)) {
    return "생년월일 6자리를 입력해주세요.";
  }

  if (!isValidBirthDate(birthDate)) {
    return "존재하지 않는 생년월일입니다.";
  }

  if (!/^[1-4]$/.test(genderCode)) {
    return "성별코드는 1~4 중 하나를 입력해주세요.";
  }

  return "";
};
