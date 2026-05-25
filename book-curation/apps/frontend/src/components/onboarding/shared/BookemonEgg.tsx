type BookemonEggProps = {
  imageUrl?: string | null;
};

export default function BookemonEgg({ imageUrl }: BookemonEggProps) {
  if (imageUrl) {
    return (
      <img
        src={imageUrl}
        alt="북케몬 알"
        className="mx-auto h-44 w-44 rounded-3xl object-contain shadow-sm"
      />
    );
  }

  return (
    <div className="mx-auto flex h-44 w-44 items-center justify-center rounded-full bg-primary/10 shadow-sm">
      <div className="h-36 w-28 rounded-[50%] border border-primary/30 bg-background shadow-inner" />
    </div>
  );
}
