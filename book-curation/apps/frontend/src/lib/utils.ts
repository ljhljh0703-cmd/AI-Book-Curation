import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** 수정 포인트: shadcn/ui 방식의 className 병합 유틸을 추가했다. */
export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));
