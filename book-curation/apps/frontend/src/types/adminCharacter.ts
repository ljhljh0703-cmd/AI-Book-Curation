export type CharacterLevelImage = {
  level: number;
  imageUrl: string;
  originalFilename: string | null;
  contentType: string | null;
  sizeBytes: number | null;
};

export type AdminCharacter = {
  id: number;
  characterKey: string;
  defaultName: string;
  level1Image: CharacterLevelImage;
  level2Image: CharacterLevelImage;
  level3Image: CharacterLevelImage;
  level4Image: CharacterLevelImage;
  createdAt: string;
  updatedAt: string;
};

export type CharacterLevelImageRequest = {
  imageUrl: string;
  originalFilename?: string | null;
  contentType?: string | null;
  sizeBytes?: number | null;
};

export type AdminCharacterRequest = {
  characterKey: string;
  defaultName: string;
  level1Image: CharacterLevelImageRequest;
  level2Image: CharacterLevelImageRequest;
  level3Image: CharacterLevelImageRequest;
  level4Image: CharacterLevelImageRequest;
};

export type AdminCharacterImageUploadResponse = {
  imageUrl: string;
  originalFilename: string | null;
  contentType: string;
  sizeBytes: number;
  width: number;
  height: number;
};
